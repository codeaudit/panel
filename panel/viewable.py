"""
Defines the Viewable and Reactive baseclasses allow all panel objects
to display themselves, communicate with a Python process and react in
response to changes to parameters and the underlying bokeh models.
"""

from __future__ import absolute_import

import re
import signal
from functools import partial
from collections import defaultdict

import param

from bokeh.application.handlers import FunctionHandler
from bokeh.application import Application
from bokeh.document import Document
from bokeh.io import curdoc, show
from bokeh.models import CustomJS
from bokeh.server.server import Server
from pyviz_comms import JS_CALLBACK, CommManager, JupyterCommManager

from .util import render_mimebundle, add_to_doc, push


class Viewable(param.Parameterized):
    """
    Viewable is the baseclass all objects in the panel library are
    built on. It defines the interface for declaring any object that
    displays itself by transforming the object(s) being wrapped into
    models that can be served using bokeh's layout engine. The class
    also defines various methods that allow Viewable objects to be
    displayed in the notebook and on bokeh server.
    """

    __abstract = True

    _comm_manager = CommManager

    _views = {}

    def __init__(self, **params):
        super(Viewable, self).__init__(**params)
        self._documents = {}

    def _get_model(self, doc, root=None, parent=None, comm=None):
        """
        Converts the objects being wrapped by the viewable into a
        bokeh model that can be composed in a bokeh layout.

        doc: bokeh.Document
          Bokeh document the bokeh model will be attached to.

        root: bokeh.Model
          The root layout the viewable will become part of.

        parent: bokeh.Model
          The parent layout the viewable will become part of.

        comm: pyviz_comms.Comm
          Optional pyviz_comms when working in notebook
        """

    def _get_root(self, doc, comm=None):
        """
        Returns the root model

        doc: bokeh.Document
          Bokeh document the bokeh model will be attached to.

        comm: pyviz_comms.Comm
          Optional pyviz_comms when working in notebook
        """
        return self._get_model(doc, comm=comm)

    def _cleanup(self, model=None, final=False):
        """
        Clean up method which is called when a Viewable is destroyed.

        model: bokeh.model.Model
            Bokeh model for the view being cleaned up

        final: boolean
            Whether the Viewable should be destroyed entirely
        """

    def _repr_mimebundle_(self, include=None, exclude=None):
        Viewable._comm_manager = JupyterCommManager
        doc = Document()
        comm = self._comm_manager.get_server_comm()
        model = self._get_root(doc, comm)
        Viewable._views[model.ref['id']] = (self, model)
        return render_mimebundle(model, doc, comm)

    def _server_destroy(self, session_context):
        doc = session_context._document
        self._cleanup(self._documents[doc], final=self._temporary)
        del self._documents[doc]

    def server_doc(self, doc=None, title=None):
        doc = doc or curdoc()
        if title is not None:
            doc.title = title
        model = self._get_root(doc)
        if hasattr(doc, 'on_session_destroyed'):
            doc.on_session_destroyed(self._server_destroy)
            self._documents[doc] = model
        add_to_doc(model, doc)
        return doc

    def servable(self):
        """
        Serves the object if in a `bokeh serve` context and returns
        it to allow it to render itself in a notebook.
        """
        if curdoc().session_context:
            self.server_doc()
        return self

    def _modify_doc(self, doc):
        return self.server_doc(doc)

    def app(self, notebook_url="localhost:8888"):
        """
        Displays a bokeh server app in the notebook.
        """
        show(self._modify_doc, notebook_url=notebook_url)

    def show(self, port=0, websocket_origin=None):
        """
        Starts a bokeh server and displays the Viewable in a new tab
        """
        def modify_doc(doc):
            return self.server_doc(doc)
        handler = FunctionHandler(modify_doc)
        app = Application(handler)

        from tornado.ioloop import IOLoop
        loop = IOLoop.current()
        if websocket_origin and not isinstance(websocket_origin, list):
            websocket_origin = [websocket_origin]
        opts = dict(allow_websocket_origin=websocket_origin) if websocket_origin else {}
        opts['io_loop'] = loop
        server = Server({'/': app}, port=port, **opts)
        def show_callback():
            server.show('/')
        server.io_loop.add_callback(show_callback)
        server.start()

        def sig_exit(*args, **kwargs):
            loop.add_callback_from_signal(do_stop)

        def do_stop(*args, **kwargs):
            loop.stop()

        signal.signal(signal.SIGINT, sig_exit)
        try:
            loop.start()
        except RuntimeError:
            pass
        return server



class Reactive(Viewable):
    """
    Reactive is a Viewable object that also supports syncing between
    the objects parameters and the underlying bokeh model either via
    the defined pyviz_comms.Comm type or when using bokeh server.

    In order to link parameters with bokeh model instances the
    _link_params and _link_props methods may be called in the
    _get_model method. Since there may not be a 1-to-1 mapping between
    parameter and the model property the _process_property_change and
    _process_param_change may be overridden to apply any necessary
    transformations.
    """

    # Timeout if a notebook comm message is swallowed
    _timeout = 20000

    # Timeout before the first event is processed
    _debounce = 50

    # Mapping from parameter name to bokeh model property name
    _rename = {}

    def __init__(self, **params):
        # temporary flag denotes panes created for temporary, internal
        # use which should be garbage collected once they have been used
        self._temporary = params.pop('_temporary', False)
        super(Reactive, self).__init__(**params)
        self._active = []
        self._events = {}
        self._expecting = []
        self._callbacks = defaultdict(list)

    def link(self, obj, **links):
        """
        Links the parameters on this object to parameters on another
        object.

        obj: object

        links: dict
            Maps between parameters on this object to the parameters
            on the supplied object.
        """
        _updating = []
        def link(*events):
            for event in events:
                if event.name in _updating: continue
                _updating.append(event.name)
                setattr(obj, links[event.name], event.new)
                _updating.pop(_updating.index(event.name))
        self._callbacks['instance'].append(self.param.watch(link, list(links)))

    def _cleanup(self, model=None, final=False):
        super(Reactive, self)._cleanup(model, final)
        if final:
            watchers = self._callbacks.pop('instance', [])
            for watcher in watchers:
                obj = watcher.cls if watcher.inst is None else watcher.inst
                obj.param.unwatch(watcher)

        if model is None:
            return

        callbacks = self._callbacks.pop(model.ref['id'], {})
        for watcher in callbacks:
            obj = watcher.cls if watcher.inst is None else watcher.inst
            obj.param.unwatch(watcher)

        # Clean up comms
        customjs = model.select({'type': CustomJS})
        pattern = "data\['comm_id'\] = \"(.*)\""
        for js in customjs:
            comm_ids = list(re.findall(pattern, js.code))
            if not comm_ids:
                continue
            comm_id = comm_ids[0]
            comm = self._comm_manager._comms.pop(comm_id, None)
            if comm:
                comm.close()


    def _process_property_change(self, msg):
        """
        Transform bokeh model property changes into parameter updates.
        Should be overridden to provide appropriate mapping between
        parameter value and bokeh model change. By default uses the
        _rename class level attribute to map between parameter and
        property names.
        """
        inverted = {v: k for k, v in self._rename.items()}
        return {inverted.get(k, k): v for k, v in msg.items()}

    def _process_param_change(self, msg):
        """
        Transform parameter changes into bokeh model property updates.
        Should be overridden to provide appropriate mapping between
        parameter value and bokeh model change. By default uses the
        _rename class level attribute to map between parameter and
        property names.
        """
        return {self._rename.get(k, k): v for k, v in msg.items()}

    def _link_params(self, model, params, doc, root, comm=None):
        def param_change(*events):
            msgs = []
            for event in events:
                msg = self._process_param_change({event.name: event.new})
                msg = {k: v for k, v in msg.items() if k not in self._active}
                if msg:
                    msgs.append(msg)

            if not msgs: return

            def update_model():
                for msg in msgs:
                    model.update(**msg)

            if comm:
                self._expecting += [m for msg in msgs for m in msg]
                update_model()
                push(doc, comm)
            else:
                doc.add_next_tick_callback(update_model)

        ref = model.ref['id']
        watcher = self.param.watch(param_change, params)
        self._callbacks[ref].append(watcher)

    def _link_props(self, model, properties, doc, root, comm=None):
        if comm is None:
            for p in properties:
                model.on_change(p, partial(self._server_change, doc))
        else:
            client_comm = self._comm_manager.get_client_comm(on_msg=self._comm_change)
            for p in properties:
                customjs = self._get_customjs(p, client_comm, root.ref['id'])
                model.js_on_change(p, customjs)

    def _comm_change(self, msg):
        filtered = {k: v for k, v in msg.items() if k not in self._expecting}
        self._expecting = [m for m in self._expecting if m not in msg]
        if not filtered:
            return
        self._events.update(filtered)
        self._active = list(self._events)
        self._change_event()

    def _server_change(self, doc, attr, old, new):
        self._events.update({attr: new})
        if not self._active:
            doc.add_timeout_callback(self._change_event, self._debounce)
        self._active = list(self._events)

    def _change_event(self):
        self.set_param(**self._process_property_change(self._events))
        self._events = {}
        self._active = []

    def _get_customjs(self, change, client_comm, plot_id):
        """
        Returns a CustomJS callback that can be attached to send the
        model state across the notebook comms.
        """
        data_template = "data = {{{change}: cb_obj['{change}']}};"
        fetch_data = data_template.format(change=change)
        self_callback = JS_CALLBACK.format(comm_id=client_comm.id,
                                           timeout=self._timeout,
                                           debounce=self._debounce,
                                           plot_id=plot_id)
        js_callback = CustomJS(code='\n'.join([fetch_data,
                                               self_callback]))
        return js_callback

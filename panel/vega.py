from __future__ import division

import os
import sys

import numpy as np
from bokeh.core.properties import Dict, String, Any, Instance
from bokeh.models import LayoutDOM, ColumnDataSource

from .pane import PaneBase


def ds_as_cds(dataset):
    """
    Converts vega dataset into bokeh ColumnDataSource data
    """
    if len(dataset) == 0:
        return {}
    data = {k: [] for k, v in dataset[0].items()}
    for item in dataset:
        for k, v in item.items():
            data[k].append(v)
    data = {k: np.asarray(v) for k, v in data.items()}
    return data


class VegaPlot(LayoutDOM):
    """
    A bokeh model that wraps around a plotly plot and renders it inside
    a bokeh plot.
    """

    __implementation__ = os.path.join(os.path.dirname(__file__), 'models', 'vega.ts')

    data = Dict(String, Any)

    data_sources = Dict(String, Instance(ColumnDataSource))


class Vega(PaneBase):
    """
    Vega panes allow rendering plotly Figures and traces.

    For efficiency any array objects found inside a Figure are added
    to a ColumnDataSource which allows using binary transport to sync
    the figure on bokeh server and via Comms.
    """

    _updates = True

    def __init__(self, object, **params):
        super(Vega, self).__init__(object, **params)

    @classmethod
    def is_altair(cls, obj):
        if 'altair' in sys.modules:
            import altair as alt
            return isinstance(obj, alt.vegalite.v2.api.Chart)
        return False

    @classmethod
    def applies(cls, obj):
        if isinstance(obj, dict) and 'vega' in obj.get('$schema', '').lower():
            return True
        return cls.is_altair(obj)

    @classmethod
    def _to_json(cls, obj):
        return obj if isinstance(obj, dict) else obj.to_dict()

    def _get_sources(self, json, sources):
        for name, data in json.pop('datasets', {}).items():
            if name in sources:
                continue
            columns = set(data[0]) if data else []
            if self.is_altair(self.object):
                import altair as alt
                if (not isinstance(self.object.data, alt.Data) and
                    columns == set(self.object.data)):
                    data = ColumnDataSource.from_df(self.object.data)
                else:
                    data = ds_as_cds(data)
                sources[name] = ColumnDataSource(data=data)
            else:
                sources[name] = ColumnDataSource(data=ds_as_cds(data))

    def _get_model(self, doc, root, parent=None, comm=None):
        """
        Should return the bokeh model to be rendered.
        """
        json = self._to_json(self.object)
        sources = {}
        self._get_sources(json, sources)
        model = VegaPlot(data=json, data_sources=sources)
        self._link_object(model, doc, root, parent, comm)
        return model

    def _update(self, model):
        json = self._to_json(self.object)
        self._get_sources(json, model.data_sources)
        model.data = json

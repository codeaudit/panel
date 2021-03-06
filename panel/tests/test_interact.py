from bokeh.models import (Div as BkDiv, Column as BkColumn,
                          WidgetBox as BkWidgetBox, Paragraph as BkParagraph)

from panel.interact import interact, interact_manual
from panel import widgets

from .test_layout import get_div


def test_boolean_interact():
    def test(a):
        return a

    interactive = interact(test, a=False)
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.Checkbox)
    assert widget.value == False

def test_string_interact():
    def test(a):
        return a

    interactive = interact(test, a='')
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.TextInput)
    assert widget.value == ''

def test_integer_interact():
    def test(a):
        return a

    interactive = interact(test, a=1)
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.IntSlider)
    assert widget.value == 1
    assert widget.start == -1
    assert widget.step == 1
    assert widget.end == 3

def test_tuple_int_range_with_step_interact():
    def test(a):
        return a

    interactive = interact(test, a=(0, 4, 2))
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.IntSlider)
    assert widget.value == 2
    assert widget.start == 0
    assert widget.step == 2
    assert widget.end == 4

def test_tuple_int_range_interact():
    def test(a):
        return a

    interactive = interact(test, a=(0, 4))
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.IntSlider)
    assert widget.value == 2
    assert widget.start == 0
    assert widget.step == 1
    assert widget.end == 4

def test_tuple_float_range_interact():
    def test(a):
        return a

    interactive = interact(test, a=(0, 4, 0.1))
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.FloatSlider)
    assert widget.value == 2
    assert widget.start == 0
    assert widget.step == 0.1
    assert widget.end == 4

def test_tuple_float_range_interact_with_default():
    def test(a=3.1):
        return a

    interactive = interact(test, a=(0, 4, 0.1))
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.FloatSlider)
    assert widget.value == 3.1
    assert widget.start == 0
    assert widget.step == 0.1
    assert widget.end == 4

def test_tuple_range_interact_with_default_of_different_type():
    def test(a=3.1):
        return a

    interactive = interact(test, a=(0, 4))
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.FloatSlider)
    assert widget.value == 3.1
    assert widget.start == 0
    assert widget.end == 4

def test_numeric_list_interact():
    def test(a):
        return a

    interactive = interact(test, a=[1, 3, 5])
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.DiscreteSlider)
    assert widget.value == 1
    assert widget.options == [1, 3, 5]

def test_string_list_interact():
    def test(a):
        return a

    options = ['A', 'B', 'C']
    interactive = interact(test, a=options)
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.Select)
    assert widget.value == 'A'
    assert widget.options == dict(zip(options, options))

def test_manual_interact():
    def test(a):
        return a

    interactive = interact_manual(test, a=False)
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.Checkbox)
    assert widget.value == False
    assert isinstance(interactive._widgets['manual'], widgets.Button)

def test_interact_updates_panel(document, comm):
    def test(a):
        return a

    interactive = interact(test, a=False)
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.Checkbox)
    assert widget.value == False

    column = interactive._get_model(document, comm=comm)
    assert isinstance(column, BkColumn)
    box = column.children[1]
    div = get_div(box)
    assert div.text == '<pre>False</pre>'
    
    widget.value = True
    assert div.text == '<pre>True</pre>'

def test_interact_replaces_panel(document, comm):
    def test(a):
        return a if a else BkDiv(text='Test')

    interactive = interact(test, a=False)
    pane = interactive._pane
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.Checkbox)
    assert widget.value == False

    column = interactive._get_model(document, comm=comm)
    assert isinstance(column, BkColumn)
    box = column.children[1]
    div = get_div(box)
    assert div.text == 'Test'
    
    widget.value = True
    assert pane._callbacks == {}
    div = get_div(column.children[1])
    assert div.text == '<pre>True</pre>'

def test_interact_replaces_model(document, comm):
    def test(a):
        return BkParagraph(text='Pre Test') if a else BkDiv(text='Test')

    interactive = interact(test, a=False)
    pane = interactive._pane
    widget = interactive._widgets['a']
    assert isinstance(widget, widgets.Checkbox)
    assert widget.value == False

    column = interactive._get_model(document, comm=comm)
    assert isinstance(column, BkColumn)
    box = column.children[1]
    assert isinstance(box, BkWidgetBox)
    div = box.children[0]
    assert isinstance(div, BkDiv)
    assert div.text == 'Test'
    assert column.ref['id'] in interactive._callbacks
    assert box.ref['id'] in pane._callbacks
    
    widget.value = True
    assert box.ref['id'] not in pane._callbacks
    new_box = column.children[1]
    pre = new_box.children[0]
    assert isinstance(pre, BkParagraph)
    assert pre.text == 'Pre Test'
    assert column.ref['id'] in interactive._callbacks
    assert new_box.ref['id'] in pane._callbacks

    interactive._cleanup(column)
    assert interactive._callbacks == {}
    assert pane._callbacks == {}

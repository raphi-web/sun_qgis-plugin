"""Tests for the shipped .ui defaults (tripwires on the XML itself).

Per user feedback:
- GPU acceleration checked by default
- optional input combos allow an empty selection (plugin sets them to None
  in SunDialog.__init__; only elevation gets a default layer)
"""
import xml.etree.ElementTree as ET

import pytest


@pytest.fixture(scope="module")
def ui_tree(core):
    from pathlib import Path

    ui = Path(core.__file__).parent / "ui" / "sun_dialog.ui"
    return ET.parse(ui)


def _widget(root, name):
    for w in root.iter("widget"):
        if w.get("name") == name:
            return w
    raise AssertionError(f"widget {name!r} not in .ui")


def _prop(widget, prop_name):
    for p in widget.findall("property"):
        if p.get("name") == prop_name:
            return p
    return None


def test_gpu_checkbox_defaults_to_checked(ui_tree):
    w = _widget(ui_tree.getroot(), "mGpu")
    p = _prop(w, "checked")
    assert p is not None, "mGpu has no 'checked' property"
    assert p.find("bool").text == "true"


@pytest.mark.parametrize(
    "name", ["mSlope", "mAspect", "mLinkeRaster", "mAlbedoRaster", "mMask"]
)
def test_optional_combos_allow_empty_selection(ui_tree, name):
    w = _widget(ui_tree.getroot(), name)
    p = _prop(w, "allowEmptyLayer")
    assert p is not None, f"{name} missing allowEmptyLayer property"
    assert p.find("bool").text == "true"

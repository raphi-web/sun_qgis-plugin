"""Tests for sun_qgis.sun_dialog.form_from_dialog — widget state -> form dict.

The real dialog needs Qt/QGIS; form_from_dialog only reads attributes, so a
SimpleNamespace with the same widget surface is enough to test the mapping.
Inputs are QgsMapLayerComboBox (currentLayer() -> layer.source()).
"""
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def dialog_module(core):
    """Load sun_dialog with qgis/PyQt mocked (conftest does the mocking)."""
    import importlib.util
    import sys

    _register = sys.modules.get("sunqgis")
    assert _register is not None, "conftest must register the sunqgis package"
    spec = importlib.util.spec_from_file_location(
        "sunqgis.sun_dialog", str(core.__file__).replace("core.py", "sun_dialog.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sunqgis.sun_dialog"] = mod
    spec.loader.exec_module(mod)
    return mod


def _layer(source):
    return SimpleNamespace(source=lambda: source, isValid=lambda: True)


class _LayerCombo:
    """Fake QgsMapLayerComboBox."""

    def __init__(self, layer=None):
        self._layer = layer

    def currentLayer(self):
        return self._layer


class _FileWidget:
    def __init__(self, value=""):
        self._value = value

    def filePath(self):
        return self._value


class _ValueWidget:
    def __init__(self, v):
        self._v = v

    def value(self):
        return self._v


class _CheckWidget:
    def __init__(self, checked=False):
        self._c = checked

    def isChecked(self):
        return self._c


def _fake_dialog(**over):
    d = SimpleNamespace(
        mElevation=_LayerCombo(_layer("/data/dem.tif")),
        mSlope=_LayerCombo(None),
        mAspect=_LayerCombo(None),
        mLinkeRaster=_LayerCombo(None),
        mAlbedoRaster=_LayerCombo(None),
        mMask=_LayerCombo(None),
        mOutputDir=_FileWidget("/out"),
        mPrefix=SimpleNamespace(text=lambda: "sol"),
        tabModes=SimpleNamespace(currentIndex=lambda: 0),
        mDay=_ValueWidget(172),
        mStep=_ValueWidget(0.5),
        mLinkeValue=_ValueWidget(3.0),
        mAlbedoValue=_ValueWidget(0.2),
        mGlob=_CheckWidget(True),
        mBeam=_CheckWidget(False),
        mDiff=_CheckWidget(False),
        mRefl=_CheckWidget(False),
        mInsol=_CheckWidget(True),
        mDayStart=_ValueWidget(1),
        mDayEnd=_ValueWidget(365),
        mDayStep=_ValueWidget(10),
        mPanelEff=_ValueWidget(0.21),
        mAnnualStep=_ValueWidget(0.5),
        mUseHorizon=_CheckWidget(False),
        mHorizonNAz=_ValueWidget(64),
        mGpu=_CheckWidget(True),
        mAddToProject=_CheckWidget(True),
    )
    for k, v in over.items():
        setattr(d, k, v)
    return d


def test_daily_tab_maps_to_daily_form(dialog_module):
    form = dialog_module.form_from_dialog(_fake_dialog())
    assert form["mode"] == "daily"
    assert form["elevation"] == "/data/dem.tif"
    assert form["day"] == 172
    assert form["step"] == 0.5
    assert form["want_glob"] is True
    assert form["want_insol"] is True
    assert form["want_beam"] is False
    assert form["output_dir"] == "/out"
    assert form["output_prefix"] == "sol"
    assert form["gpu"] is True
    # unselected optional layer combos become None
    assert form["slope"] is None
    assert form["mask"] is None


def test_optional_layer_paths_forwarded(dialog_module):
    form = dialog_module.form_from_dialog(
        _fake_dialog(mSlope=_LayerCombo(_layer("/data/slope.tif")))
    )
    assert form["slope"] == "/data/slope.tif"


def test_layer_subdataset_suffix_is_stripped(dialog_module):
    """QGIS appends '|layername=…' to some sources; the native engine opens
    plain paths, so the suffix must be removed."""
    form = dialog_module.form_from_dialog(
        _fake_dialog(
            mElevation=_LayerCombo(_layer("/data/dem.gpkg|layername=band 1"))
        )
    )
    assert form["elevation"] == "/data/dem.gpkg"


def test_no_elevation_layer_gives_empty_string_for_validation(dialog_module):
    form = dialog_module.form_from_dialog(_fake_dialog(mElevation=_LayerCombo(None)))
    assert form["elevation"] == ""


def test_annual_tab_maps_to_annual_form(dialog_module):
    form = dialog_module.form_from_dialog(
        _fake_dialog(tabModes=SimpleNamespace(currentIndex=lambda: 1))
    )
    assert form["mode"] == "annual"
    assert form["day_start"] == 1
    assert form["day_end"] == 365
    assert form["day_step"] == 10
    assert form["panel_efficiency"] == 0.21
    assert form["step"] == 0.5
    assert form["use_horizon"] is False
    assert form["horizon_n_az"] == 64


def test_form_from_dialog_roundtrips_through_validate(core, dialog_module):
    """The dialog's form dict must satisfy the core contract end to end."""
    form = dialog_module.form_from_dialog(_fake_dialog())
    assert core.validate_form(form) == []
    assert form["elevation"].startswith("/data/dem.tif")

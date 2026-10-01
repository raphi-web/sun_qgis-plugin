"""Dialog for the sun_qgis plugin.

form_from_dialog() is the testable core: it reads widget state into the plain
dict consumed by sun_qgis.core.validate_form / build_*_kwargs. The SunDialog
class below is thin Qt glue (not unit-tested headless).
"""

import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

FORM_DIR = os.path.join(os.path.dirname(__file__), "ui")
UI_FILE = os.path.join(FORM_DIR, "sun_dialog.ui")

DAILY_TAB = 0
ANNUAL_TAB = 1


def _file_path_or_none(widget):
    """QgsFileWidget.filePath() returns '' when empty; normalize to None."""
    path = widget.filePath()
    return str(path) if path else None


def form_from_dialog(dlg):
    """Extract the form dict from a dialog-like object (any object exposing
    the .ui widget surface: file widgets with filePath(), spins with value(),
    checkboxes with isChecked(), tab widget with currentIndex())."""
    tab = dlg.tabModes.currentIndex()
    form = {
        "elevation": _file_path_or_none(dlg.mElevation) or "",
        "slope": _file_path_or_none(dlg.mSlope),
        "aspect": _file_path_or_none(dlg.mAspect),
        "linke": _file_path_or_none(dlg.mLinkeRaster),
        "albedo": _file_path_or_none(dlg.mAlbedoRaster),
        "mask": _file_path_or_none(dlg.mMask),
        "output_dir": _file_path_or_none(dlg.mOutputDir) or "",
        "output_prefix": dlg.mPrefix.text().strip(),
        "gpu": dlg.mGpu.isChecked(),
        "linke_value": dlg.mLinkeValue.value(),
        "albedo_value": dlg.mAlbedoValue.value(),
        "mode": "daily" if tab == DAILY_TAB else "annual",
    }
    if tab == DAILY_TAB:
        form.update(
            day=dlg.mDay.value(),
            step=dlg.mStep.value(),
            want_glob=dlg.mGlob.isChecked(),
            want_beam=dlg.mBeam.isChecked(),
            want_diff=dlg.mDiff.isChecked(),
            want_refl=dlg.mRefl.isChecked(),
            want_insol=dlg.mInsol.isChecked(),
        )
    else:
        form.update(
            day_start=dlg.mDayStart.value(),
            day_end=dlg.mDayEnd.value(),
            day_step=dlg.mDayStep.value(),
            step=dlg.mAnnualStep.value(),
            panel_efficiency=dlg.mPanelEff.value(),
            use_horizon=dlg.mUseHorizon.isChecked(),
            horizon_n_az=dlg.mHorizonNAz.value(),
        )
    return form


class SunDialog(QDialog):
    """Qt dialog — glue only; logic lives in form_from_dialog + core."""

    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)

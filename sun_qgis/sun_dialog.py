"""Dialog for the sun_qgis plugin.

form_from_dialog() is the testable core: it reads widget state into the plain
dict consumed by sun_qgis.core.validate_form / build_*_kwargs. The SunDialog
class below is thin Qt glue (not unit-tested headless): it owns the Run
button, progress bar, and the SunComputationTask lifecycle so the window
stays open and shows progress until the computation finishes.
"""

import os

from qgis.core import QgsApplication, QgsMapLayerProxyModel, QgsTask
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMessageBox

FORM_DIR = os.path.join(os.path.dirname(__file__), "ui")
UI_FILE = os.path.join(FORM_DIR, "sun_dialog.ui")

DAILY_TAB = 0
ANNUAL_TAB = 1

# optional raster inputs: widget name -> filter predicate arg
_OPTIONAL_COMBOS = (
    ("mSlope", "slope"),
    ("mAspect", "aspect"),
    ("mLinkeRaster", "linke"),
    ("mAlbedoRaster", "albedo"),
    ("mMask", "mask"),
)


def _layer_path_or_none(combo):
    """QgsMapLayerComboBox -> layer file path, or None when nothing selected.

    QGIS layer sources can carry subdataset suffixes ('/x.gpkg|layername=…');
    the native engine opens plain paths, so strip everything from '|'.
    """
    layer = combo.currentLayer()
    if layer is None:
        return None
    source = layer.source()
    if not source:
        return None
    return source.split("|")[0]


def form_from_dialog(dlg):
    """Extract the form dict from a dialog-like object (any object exposing
    the .ui widget surface: layer combos with currentLayer(), file widgets
    with filePath(), spins with value(), checkboxes with isChecked(), tab
    widget with currentIndex())."""
    tab = dlg.tabModes.currentIndex()
    form = {
        "elevation": _layer_path_or_none(dlg.mElevation) or "",
        "slope": _layer_path_or_none(dlg.mSlope),
        "aspect": _layer_path_or_none(dlg.mAspect),
        "linke": _layer_path_or_none(dlg.mLinkeRaster),
        "albedo": _layer_path_or_none(dlg.mAlbedoRaster),
        "mask": _layer_path_or_none(dlg.mMask),
        "output_dir": dlg.mOutputDir.filePath() or "",
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
    """Qt dialog: Run starts a background SunComputationTask and keeps the
    window open, streaming progress into mProgress/mStatus until done."""

    def __init__(self, parent=None, run_computation=None):
        """*run_computation*: callable(task, form) that starts the background
        task (injected by the plugin; defaults to the QGIS task manager)."""
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)

        # Inputs: raster layers only
        for combo in (self.mElevation,) + tuple(
            getattr(self, name) for name, _ in _OPTIONAL_COMBOS
        ):
            combo.setFilters(QgsMapLayerProxyModel.RasterLayer)

        # Elevation keeps whatever QGIS preselected (usually the active
        # layer); the optional inputs must start empty — silently computing
        # against some random preselected slope/mask would be worse than
        # forcing an explicit choice.
        for name, _ in _OPTIONAL_COMBOS:
            getattr(self, name).setLayer(None)

        self._run_computation = run_computation
        self._task = None

        # Manual Run/Close: OK would close the window before the job starts.
        self.buttonBox.setStandardButtons(
            QDialogButtonBox.Close | QDialogButtonBox.Ok
        )
        self.buttonBox.button(QDialogButtonBox.Ok).setText("Run")
        self.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self._on_run)
        self.buttonBox.rejected.connect(self._on_close_requested)

    # ── run lifecycle ────────────────────────────────────────────────────
    def _on_run(self):
        from . import core
        from .task import SunComputationTask

        form = form_from_dialog(self)
        errors = core.validate_form(form)
        if errors:
            QMessageBox.warning(self, "Solar Radiation (sun)", "\n".join(errors))
            return

        try:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            sun = core.load_sun(plugin_dir)
        except Exception as e:
            QMessageBox.critical(
                self, "Solar Radiation (sun)", f"Could not load the sun extension:\n{e}"
            )
            return

        task = SunComputationTask("Solar radiation computation", sun, form)
        # NOTE: taskCompleted() carries NO arguments — never bind a lambda
        # with parameters to it (raises 'missing 1 required positional
        # argument' inside the signal dispatch).
        task.taskCompleted.connect(self._on_task_done)
        task.progressChanged.connect(self._on_progress)
        task.taskTerminated.connect(self._on_terminated)
        self._task = task
        self._set_running(True)
        self.mStatus.setText("Starting computation…")

        if self._run_computation is not None:
            self._run_computation(task, form)
        else:
            QgsApplication.taskManager().addTask(task)

    def _on_progress(self, pct):
        self.mProgress.setValue(int(pct))
        self.mStatus.setText(f"Computing… {int(pct)}%")

    def _on_task_done(self):
        from . import core  # noqa: F401  (kept for symmetry; glue only)

        task, self._task = self._task, None
        self._set_running(False)
        if task is not None and task.outputs:
            self.mProgress.setValue(100)
            self.mStatus.setText(
                f"Done — {len(task.outputs)} raster(s) written to "
                f"{os.path.dirname(task.outputs[0])}"
            )
            self.finished_ok(task.outputs)
        else:
            msg = getattr(task, "error_message", None) or "Computation failed."
            self.mStatus.setText("Failed.")
            QMessageBox.critical(self, "Solar Radiation (sun)", msg)

    def _on_terminated(self):
        self._task = None
        self._set_running(False)
        self.mStatus.setText("Cancelled.")

    def finished_ok(self, outputs):
        """Overridden/injected by the plugin to add layers to the project."""

    # ── widget state ─────────────────────────────────────────────────────
    def _set_running(self, running):
        self.mProgress.setVisible(True)
        self.mStatus.setVisible(True)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(not running)
        self.buttonBox.button(QDialogButtonBox.Close).setEnabled(not running)
        self.tabModes.setEnabled(not running)
        self.groupInputs.setEnabled(not running)
        self.groupOutput.setEnabled(not running)
        if running:
            self.mProgress.setRange(0, 100)
            self.mProgress.setValue(0)

    def _on_close_requested(self):
        if self._task is not None and not self._task.isCanceled():
            self._task.cancel()
        self.reject()

    def closeEvent(self, event):
        if self._task is not None:
            self._task.cancel()
        super().closeEvent(event)

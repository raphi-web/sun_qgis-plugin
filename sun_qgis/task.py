"""QgsTask wrapper around the tiled sun pipeline.

run_sun_task(sun, form) is the testable core: validates the form, delegates
to pipeline.run_tiled (Python GDAL I/O around the native array API), and
returns the list of written files. SunComputationTask is QGIS glue
(progress + cancellation surface).
"""

from qgis.core import QgsTask

from . import pipeline


def run_sun_task(sun, form, progress_cb=None, band_rows=None, canceled_check=None):
    """Validate *form*, run the tiled computation, return output paths.

    *progress_cb* (if given) receives monotonically increasing 0..100 floats,
    reported by the pipeline after each completed row band — no stderr
    capture needed, since the native calls run quiet and the band loop
    drives progress from Python.

    *band_rows* optionally overrides the pipeline's default band height
    (rows processed per native call; smaller = less memory for optional
    inputs/outputs on huge DEMs).

    *canceled_check* (if given) is called before each band; return True to
    abort the computation with RuntimeError("cancel").

    Raises ValueError with the validation errors joined; native/IO failures
    propagate untouched.
    """
    kwargs = {"progress_cb": progress_cb, "canceled_check": canceled_check}
    if band_rows is not None:
        kwargs["band_rows"] = int(band_rows)
    return pipeline.run_tiled(sun, form, **kwargs)


class SunComputationTask(QgsTask):
    """Runs run_sun_task off the GUI thread; stores results on the task.

    Progress: the pipeline's per-band callbacks are forwarded via
    task.setProgress() (thread-safe; the GUI sees progressChanged).
    """

    def __init__(self, description, sun, form, band_rows=None):
        super().__init__(description, QgsTask.CanCancel)
        self.sun = sun
        self.form = form
        self.band_rows = band_rows
        self.outputs = []
        self.error_message = None

    def run(self):
        try:
            self.outputs = run_sun_task(
                self.sun,
                self.form,
                progress_cb=self.setProgress,
                band_rows=self.band_rows,
                canceled_check=self.isCanceled,
            )
            return True
        except Exception as e:  # surfaced to the GUI thread in finished()
            self.error_message = str(e)
            return False

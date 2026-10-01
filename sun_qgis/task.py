"""QgsTask wrapper around the native sun extension.

run_sun_task(sun, form) is the testable core: validates, builds kwargs,
dispatches to the right native function, returns the list of written files.
SunComputationTask is QGIS glue (progress + cancellation surface).
"""

from qgis.core import QgsTask

from . import core


def run_sun_task(sun, form, progress_cb=None):
    """Validate *form*, run the matching sun computation, return output paths.

    When *progress_cb* is given, the native engine runs with quiet=False and
    its C-level stderr progress reports ('Progress: NN%') are streamed to
    progress_cb(percent_float) via core.run_capturing_stderr.

    Raises ValueError with the validation errors joined; native failures
    (RuntimeError from the extension) propagate untouched.
    """
    errors = core.validate_form(form)
    if errors:
        raise ValueError("\n".join(errors))

    if form.get("mode") == "annual":
        kwargs = core.build_annual_kwargs(form)
        dispatch = sun.compute_annual_potential
        outputs = [kwargs["out_path"]]
    else:
        kwargs = core.build_daily_kwargs(form)
        dispatch = sun.compute_raster
        outputs = [
            kwargs[k] for _, k, _ in core.DAILY_OUTPUTS if kwargs[k] is not None
        ]

    if progress_cb is None:
        dispatch(**kwargs)  # kwargs already carry quiet=True
    else:
        kwargs["quiet"] = False
        core.run_capturing_stderr(lambda: dispatch(**kwargs), progress_cb)
    return outputs


class SunComputationTask(QgsTask):
    """Runs run_sun_task off the GUI thread; stores results on the task.

    Progress: the native 'Progress: NN%' reports are forwarded via
    task.setProgress() (thread-safe; the GUI sees progressChanged).
    """

    def __init__(self, description, sun, form):
        super().__init__(description, QgsTask.CanCancel)
        self.sun = sun
        self.form = form
        self.outputs = []
        self.error_message = None

    def run(self):
        try:
            self.outputs = run_sun_task(
                self.sun, self.form, progress_cb=self.setProgress
            )
            return True
        except Exception as e:  # surfaced to the GUI thread in finished()
            self.error_message = str(e)
            return False

"""QgsTask wrapper around the native sun extension.

run_sun_task(sun, form) is the testable core: validates, builds kwargs,
dispatches to the right native function, returns the list of written files.
SunComputationTask is QGIS glue (progress + cancellation surface).
"""

from qgis.core import QgsTask

from . import core


def run_sun_task(sun, form):
    """Validate *form*, run the matching sun computation, return output paths.

    Raises ValueError with the validation errors joined; native failures
    (RuntimeError from the extension) propagate untouched.
    """
    errors = core.validate_form(form)
    if errors:
        raise ValueError("\n".join(errors))

    if form.get("mode") == "annual":
        kwargs = core.build_annual_kwargs(form)
        sun.compute_annual_potential(**kwargs)
        return [kwargs["out_path"]]

    kwargs = core.build_daily_kwargs(form)
    sun.compute_raster(**kwargs)
    return [kwargs[k] for _, k, _ in core.DAILY_OUTPUTS if kwargs[k] is not None]


class SunComputationTask(QgsTask):
    """Runs run_sun_task off the GUI thread; stores results on the task."""

    def __init__(self, description, sun, form):
        super().__init__(description, QgsTask.CanCancel)
        self.sun = sun
        self.form = form
        self.outputs = []
        self.error_message = None

    def run(self):
        try:
            self.outputs = run_sun_task(self.sun, self.form)
            return True
        except Exception as e:  # surfaced to the GUI thread in finished()
            self.error_message = str(e)
            return False

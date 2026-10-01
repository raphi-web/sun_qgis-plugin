"""Plugin entry point — toolbar action + dialog wiring (thin glue)."""

import os

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
)
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from . import core
from .sun_dialog import SunDialog, form_from_dialog
from .task import SunComputationTask

PLUGIN_DIR = os.path.dirname(__file__)


class SunPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self._sun = None
        self._task = None

    def initGui(self):
        icon_path = os.path.join(PLUGIN_DIR, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "Solar Radiation (sun)…", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToRasterMenu("Solar Radiation (sun)", self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginRasterMenu("Solar Radiation (sun)", self.action)
            self.action = None

    def run(self):
        dlg = SunDialog(self.iface.mainWindow())
        if dlg.exec_():
            self.start_computation(form_from_dialog(dlg))

    def start_computation(self, form):
        try:
            sun = core.load_sun(PLUGIN_DIR)
        except Exception as e:
            self._fail(f"Could not load the sun extension:\n{e}")
            return

        task = SunComputationTask("Solar radiation computation", sun, form)
        task.taskCompleted.connect(lambda result, t=task: self._on_finished(t, form))
        self._task = task  # keep a reference; task manager owns it meanwhile
        QgsApplication.taskManager().addTask(task)

    def _on_finished(self, task, form):
        self._task = None
        if not task.outputs:
            self._fail(task.error_message or "Computation failed.")
            return
        self._add_layers(task.outputs)
        self.iface.messageBar().pushMessage(
            "Solar radiation",
            f"Finished — {len(task.outputs)} raster(s) written.",
            level=Qgis.Success,
            duration=5,
        )

    def _add_layers(self, paths):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            layer = QgsRasterLayer(path, name)
            if layer.isValid():
                project.addMapLayer(layer, False)
                root.insertLayer(0, layer)

    def _fail(self, message):
        QMessageBox.critical(self.iface.mainWindow(), "Solar Radiation (sun)", message)

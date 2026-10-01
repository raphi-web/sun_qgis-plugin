"""Plugin entry point — toolbar action + dialog wiring (thin glue).

The dialog owns the computation lifecycle (Run button, progress bar, task);
the plugin only opens it and hooks result loading into the project.
"""

import os

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .sun_dialog import SunDialog

PLUGIN_DIR = os.path.dirname(__file__)


class SunPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None

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
        if self.dlg is None:
            self.dlg = SunDialog(self.iface.mainWindow())
            self.dlg.finished_ok = self._add_layers
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def _add_layers(self, paths):
        add = self.dlg.mAddToProject.isChecked() if self.dlg else True
        if not add:
            return
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            layer = QgsRasterLayer(path, name)
            if layer.isValid():
                project.addMapLayer(layer, False)
                root.insertLayer(0, layer)

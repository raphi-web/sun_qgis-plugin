"""sun_qgis — QGIS plugin wrapping the GPU-accelerated `sun` solar radiation model."""


def classFactory(iface):
    from .plugin import SunPlugin

    return SunPlugin(iface)

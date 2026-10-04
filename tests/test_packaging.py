"""Release zip = plugin source only.

plugins.qgis.org rejects plugins that ship binaries. The computation engine
is the pip package sun-solar-radiation; the zip must never carry it.
"""
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BINARY_SUFFIXES = (".so", ".pyd", ".dll", ".dylib", ".exe", ".whl")


@pytest.fixture(scope="module")
def release_zip(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["bash", str(REPO / "scripts" / "build_qgis_plugin.sh")],
        check=True,
        capture_output=True,
        env={**os.environ, "DIST_DIR": str(out)},
    )
    zips = sorted(out.glob("sun_qgis_plugin-*.zip"))
    assert len(zips) == 1, zips
    return zips[0]


@pytest.fixture(scope="module")
def names(release_zip):
    with zipfile.ZipFile(release_zip) as zf:
        return zf.namelist()


def test_zip_has_no_binaries(names):
    binaries = [n for n in names if n.endswith(BINARY_SUFFIXES)]
    assert not binaries, f"release zip ships binaries: {binaries}"


def test_zip_has_runtime_files(names):
    for f in (
        "sun_qgis/__init__.py",
        "sun_qgis/plugin.py",
        "sun_qgis/core.py",
        "sun_qgis/pipeline.py",
        "sun_qgis/raster_io.py",
        "sun_qgis/task.py",
        "sun_qgis/sun_dialog.py",
        "sun_qgis/ui/sun_dialog.ui",
        "sun_qgis/metadata.txt",
        "sun_qgis/icon.png",
        "sun_qgis/LICENSE",
        "sun_qgis/README.md",
    ):
        assert f in names, f"{f} missing from release zip"


def test_zip_has_no_cache_or_hidden_files(names):
    bad = [
        n for n in names
        if "__pycache__" in n or n.endswith(".pyc")
        or any(part.startswith(".") for part in n.split("/") if part)
    ]
    assert not bad, bad


def test_zip_metadata_version_matches_name(release_zip, names):
    with zipfile.ZipFile(release_zip) as zf:
        meta = zf.read("sun_qgis/metadata.txt").decode()
    version = next(
        ln.split("=", 1)[1].strip() for ln in meta.splitlines()
        if ln.startswith("version=")
    )
    assert release_zip.name == f"sun_qgis_plugin-{version}.zip"


def test_plugin_source_dir_has_no_binaries():
    """No engine copy next to the plugin code: it would be dead weight and
    could mask a missing pip install during development."""
    found = [
        str(p.relative_to(REPO)) for p in (REPO / "sun_qgis").rglob("*")
        if p.suffix in BINARY_SUFFIXES
    ]
    assert not found, found

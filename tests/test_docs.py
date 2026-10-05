"""Tests that user-facing documentation (metadata.txt, README.md) stays
user-focused and doesn't leak implementation details.

The plugin description should sell benefits (fast solar computation), not
implementation (Rust, WebGPU, rayon). Implementation details belong in
developer docs, not in what users see in the QGIS plugin manager.
"""
import pytest
from pathlib import Path


@pytest.fixture(scope="module")
def metadata_text():
    return (Path(__file__).parent.parent / "sun_qgis" / "metadata.txt").read_text()


@pytest.fixture(scope="module")
def readme_text():
    return (Path(__file__).parent.parent / "README.md").read_text()


def test_metadata_description_no_implementation_terms(metadata_text):
    """The 'description' line users see in the plugin manager must not
    mention implementation details: Rust, WebGPU, rayon, wgpu, r.sun port."""
    # Extract the description line
    for line in metadata_text.splitlines():
        if line.startswith("description="):
            desc = line.split("=", 1)[1]
            break
    else:
        pytest.fail("metadata.txt missing 'description=' line")

    forbidden = ["rust", "webgpu", "rayon", "wgpu", "port"]
    found = [term for term in forbidden if term.lower() in desc.lower()]
    assert not found, f"description mentions implementation: {found}"


def test_metadata_about_no_implementation_details(metadata_text):
    """The 'about' block (shown in plugin details) should focus on what it
    does and why users care, not how it's built."""
    about = _about(metadata_text)

    # These are implementation details that don't belong in user-facing text
    forbidden = ["rayon", "wgpu", "rust", "shader", "backend"]
    found = [term for term in forbidden if term.lower() in about.lower()]
    assert not found, f"about mentions implementation: {found}"

    # Must mention user benefits
    required = ["solar", "radiation", "dem", "elevation"]
    missing = [term for term in required if term.lower() not in about.lower()]
    assert not missing, f"about missing user benefits: {missing}"


def test_readme_has_user_sections(readme_text):
    """README must have sections users actually need: installation, usage,
    examples, troubleshooting."""
    required_sections = [
        "install",
        "usage",
        "example",
        "troubleshoot",
    ]
    lower = readme_text.lower()
    missing = [sec for sec in required_sections if sec not in lower]
    assert not missing, f"README missing sections: {missing}"


def test_readme_no_implementation_in_intro(readme_text):
    """The first few paragraphs (what users read first) must not mention
    Rust, WebGPU, or other implementation details."""
    # First 500 chars or first 10 lines, whichever is shorter
    intro = readme_text[:500] if len(readme_text) > 500 else "\n".join(readme_text.splitlines()[:10])

    forbidden = ["rust", "webgpu", "rayon", "wgpu"]
    found = [term for term in forbidden if term.lower() in intro.lower()]
    assert not found, f"README intro mentions implementation: {found}"


def test_readme_has_performance_info(readme_text):
    """Users care about speed. README must mention performance or benchmarks."""
    lower = readme_text.lower()
    assert any(term in lower for term in ["fast", "speed", "performance", "benchmark"]), \
        "README doesn't mention performance"


def test_readme_leads_with_performance(readme_text):
    """Speed is the selling point: the benchmark is the first section."""
    headings = [ln for ln in readme_text.splitlines() if ln.startswith("## ")]
    assert headings and headings[0] == "## Performance", headings[:3]


def test_readme_has_parameter_docs(readme_text):
    """Users need to know what parameters mean. README must document them."""
    lower = readme_text.lower()
    # Must mention key parameters
    required = ["linke", "albedo", "slope", "aspect"]
    missing = [term for term in required if term.lower() not in lower]
    assert not missing, f"README missing parameter docs: {missing}"


def test_no_placeholder_metadata(readme_text, metadata_text):
    """Release docs must not ship template placeholders."""
    for text, name in ((readme_text, "README"), (metadata_text, "metadata")):
        for placeholder in ("yourusername", "example.com", "Your Name",
                            "<repository-url>"):
            assert placeholder not in text, f"{name} contains placeholder {placeholder!r}"


def test_readme_troubleshooting_matches_gdal_free_extension(readme_text):
    """The extension no longer links GDAL — troubleshooting must not tell
    users to verify GDAL linkage (stale advice from the old architecture)."""
    assert "ldd" not in readme_text or "grep gdal" not in readme_text, (
        "README still tells users to check GDAL linkage of the extension"
    )


def test_readme_documents_aspect_convention(readme_text):
    """The engine uses GRASS aspect convention (0=E, CCW). Documenting the
    wrong convention silently corrupts user-supplied aspect rasters."""
    assert "grass" in readme_text.lower(), "aspect convention undocumented"


PLUGIN_REPO = "https://github.com/raphi-web/sun_qgis-plugin"


def _metadata_field(metadata_text, key):
    for line in metadata_text.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def test_metadata_points_to_plugin_repo(metadata_text):
    """plugins.qgis.org shows repository/tracker to users: plugin bugs must
    land in the plugin repo, not the computation-engine repo."""
    assert _metadata_field(metadata_text, "repository") == PLUGIN_REPO
    assert _metadata_field(metadata_text, "tracker") == f"{PLUGIN_REPO}/issues"
    assert _metadata_field(metadata_text, "homepage") == PLUGIN_REPO


def test_readme_links_plugin_repo(readme_text):
    """README must point users at the plugin's own repo and tracker."""
    assert f"{PLUGIN_REPO}/issues" in readme_text


def _about(metadata_text):
    """Parse 'about' the way QGIS does (configparser keeps blank lines)."""
    import configparser

    cp = configparser.ConfigParser()
    cp.read_string(metadata_text)
    return " ".join(cp["general"]["about"].split())


def test_about_states_engine_dependency(metadata_text):
    """plugins.qgis.org: external dependencies must be stated in About."""
    about = _about(metadata_text)
    assert "pip install sun-solar-radiation" in about


def test_readme_install_covers_engine_on_every_platform(readme_text):
    assert "pip install sun-solar-radiation" in readme_text
    assert "OSGeo4W Shell" in readme_text, "Windows install route missing"
    assert "Contents/MacOS" in readme_text, "macOS install route missing"
    assert "--user" in readme_text, "Linux install route missing"


def test_readme_does_not_describe_bundled_binaries(readme_text):
    for name in ("sun.cpython-312-x86_64-linux-gnu.so", "sun.cp312-win_amd64.pyd",
                 "sun.cpython-312-darwin.so"):
        assert name not in readme_text, f"README still describes bundled {name}"


def test_docs_state_the_minimum_engine_version(core, readme_text, metadata_text):
    """README and About must name the version load_sun() actually enforces."""
    need = ".".join(map(str, core.MIN_ENGINE_VERSION))
    assert f"(version {need} or newer)" in readme_text
    assert f"sun-solar-radiation ({need} or newer)" in _about(metadata_text)


def test_minimum_engine_has_the_gpu_watchdog_fix(core):
    """0.1.2 splits GPU work into short submissions; older engines can make
    the graphics driver reset the GPU and take QGIS down on large DEMs."""
    assert core.MIN_ENGINE_VERSION >= (0, 1, 2)


def test_readme_explains_gpu_failure_message(readme_text):
    assert "GPU computation failed" in readme_text

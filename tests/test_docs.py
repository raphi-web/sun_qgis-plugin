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
    # Extract the about block (multi-line, starts with about=)
    lines = metadata_text.splitlines()
    about_lines = []
    in_about = False
    for line in lines:
        if line.startswith("about="):
            in_about = True
            about_lines.append(line.split("=", 1)[1])
        elif in_about:
            if line.startswith(" ") or line.startswith("\t"):
                about_lines.append(line.strip())
            else:
                break
    about = " ".join(about_lines)

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

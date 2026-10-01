"""Tests for progress plumbing: core.parse_progress_line + core.run_capturing_stderr.

The native sun engine reports progress on stderr (fd 2):
  CPU:      "\\rProgress: NN%   " (eprint!, \\r-delimited, no trailing newline)
  GPU:      "GPU  Tile N: ..." (no percentage -> parser must yield None)
run_capturing_stderr redirects fd 2 into a pipe, parses progress lines into a
callback, forwards everything else to the original stderr, and restores fd 2.
"""
import os

import pytest


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Progress: 45%", 45.0),
        ("Progress: 100%   ", 100.0),
        ("CPU annual  Progress: 12%", 12.0),
        ("GPU  Tile 3: rows 0..512, dispatch 8×8 workgroups", None),
        ("GPU annual  Tile 0: day 20/40 done", None),
        ("Day: 172  |  Declination: 23.1°", None),
        ("random noise", None),
        ("", None),
    ],
)
def test_parse_progress_line(core, line, expected):
    assert core.parse_progress_line(line) == expected


def test_run_capturing_stderr_reports_progress_in_order(core):
    seen = []

    def work():
        # Rust eprint! style: \r-prefixed, no trailing newline
        os.write(2, b"Progress: 40%")
        os.write(2, b"\rProgress: 90%   ")

    result = core.run_capturing_stderr(work, seen.append)
    assert seen == [40.0, 90.0]
    assert result is None


def test_run_capturing_stderr_returns_function_result(core):
    result = core.run_capturing_stderr(lambda: 42, lambda p: None)
    assert result == 42


def test_run_capturing_stderr_forwards_nonprogress_bytes(core):
    echoed = []

    def work():
        os.write(2, b"GPU  Tile 1: rows 0..512\n")

    core.run_capturing_stderr(work, lambda p: None, echo=echoed.append)
    assert b"GPU  Tile 1: rows 0..512" in b"".join(echoed)


def test_run_capturing_stderr_propagates_exception_and_restores_fd(core):
    def boom():
        os.write(2, b"Progress: 10%")
        raise RuntimeError("native failure")

    with pytest.raises(RuntimeError, match="native failure"):
        core.run_capturing_stderr(boom, lambda p: None)
    # fd 2 restored: writing must not explode and must not hang
    os.write(2, b"stderr still alive\n")


def test_run_capturing_stderr_handles_split_writes(core):
    """A percentage split across write boundaries must still parse."""
    seen = []

    def work():
        os.write(2, b"\rProg")
        os.write(2, b"ress: 55")
        os.write(2, b"%   \rProgress: 100%\n")

    core.run_capturing_stderr(work, seen.append)
    assert seen == [55.0, 100.0]

"""Project-wide pytest options, available before test collection starts."""

import sys
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--output-dir", type=Path, help="Keep demo SVG/PPTX pairs in this directory")


def pytest_collection_modifyitems(items):
    from mpl2pptx.pptx import powerpoint

    uses_office = sys.platform == "win32" and powerpoint.is_installed()
    for item in items:
        if "conversion_output" in item.fixturenames:
            item.add_marker(pytest.mark.integration)
            if uses_office:
                item.add_marker(pytest.mark.office)


@pytest.fixture
def conversion_output(pytestconfig):
    from mpl2pptx.pptx import get_backend

    try:
        get_backend()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    return pytestconfig.getoption("--output-dir")

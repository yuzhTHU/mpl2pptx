"""Project-wide pytest options, available before test collection starts."""

import sys
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--output-dir", type=Path, help="Keep demo SVG/PPTX pairs in this directory")


def pytest_collection_modifyitems(items):
    for item in items:
        if "office_output" in item.fixturenames:
            item.add_marker(pytest.mark.office)


@pytest.fixture
def office_output(pytestconfig):
    if sys.platform != "win32":
        pytest.skip("Requires Windows desktop PowerPoint")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CLSID"):
            pass
    except FileNotFoundError:
        pytest.skip("PowerPoint.Application is not installed")
    return pytestconfig.getoption("--output-dir")

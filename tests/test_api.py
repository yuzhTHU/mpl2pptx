"""Public Python API and binary stream behaviour."""

import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from lxml import etree as ET
from matplotlib.figure import Figure
import pytest

from mpl2pptx import api, pptx, save_pptx, svg2pptx
from mpl2pptx.namespaces import qname
from mpl2pptx.pptx import portable, powerpoint
from mpl2pptx.svg.document import read_svg


SVG = b'<svg xmlns="http://www.w3.org/2000/svg"/>'


PORTABLE_PACKAGES = ("svgslide", "mathml2omml")


@pytest.mark.parametrize(("requested", "platform", "installed", "office", "expected"), [
    (None, "win32", (), True, "powerpoint"),
    (None, "win32", PORTABLE_PACKAGES, True, "powerpoint"),
    ("auto", "win32", PORTABLE_PACKAGES, False, "portable"),
    (None, "linux", PORTABLE_PACKAGES, False, "portable"),
    (None, "win32", (), False, None),
    (None, "linux", ("svgslide",), False, None),
    ("powerpoint", "win32", PORTABLE_PACKAGES, True, "powerpoint"),
    ("powerpoint", "win32", PORTABLE_PACKAGES, False, None),
    ("powerpoint", "linux", PORTABLE_PACKAGES, False, None),
    ("portable", "win32", PORTABLE_PACKAGES, True, "portable"),
    ("portable", "win32", (), True, None),
    ("portable", "win32", ("mathml2omml",), True, None),
])
def test_backend_for_installed_dependencies(monkeypatch, requested, platform, installed, office, expected):
    monkeypatch.setattr(pptx, "sys", SimpleNamespace(platform=platform))

    def find_spec(name):
        assert requested != "powerpoint" and (requested == "portable" or not office)
        return object() if name in installed else None

    def is_installed():
        assert platform == "win32" and requested != "portable"
        return office

    monkeypatch.setattr(pptx, "find_spec", find_spec)
    monkeypatch.setattr(powerpoint, "is_installed", is_installed)
    if expected is None:
        with pytest.raises(FileNotFoundError) as failure:
            pptx.get_backend(requested)
        message = str(failure.value)
        assert ("未安装 PowerPoint" in message) == (requested != "portable")
        assert (pptx.PORTABLE_INSTALL in message) == (requested != "powerpoint")
        for package in PORTABLE_PACKAGES:
            assert (package in message) == (requested != "powerpoint" and package not in installed)
    else:
        assert pptx.get_backend(requested).NAME == expected


@pytest.mark.parametrize("location", ["app-path", "office-directory", "absent"])
def test_missing_com_registration_checks_for_desktop_application(monkeypatch, tmp_path, location):
    executable = tmp_path / "custom" / "POWERPNT.EXE"
    if location == "office-directory":
        executable = tmp_path / "Microsoft Office" / "root" / "Office16" / "POWERPNT.EXE"
    if location != "absent":
        executable.parent.mkdir(parents=True)
        executable.touch()

    def open_key(hive, key):
        raise FileNotFoundError(key)

    def query_value(hive, key):
        if hive == "machine" and location != "office-directory":
            return str(executable)
        raise FileNotFoundError(key)

    registry = SimpleNamespace(HKEY_CLASSES_ROOT="classes", HKEY_CURRENT_USER="user",
                               HKEY_LOCAL_MACHINE="machine", OpenKey=open_key, QueryValue=query_value)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.setenv(variable, str(tmp_path))
    monkeypatch.setattr(pptx, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(pptx, "find_spec", lambda name: object())
    assert pptx.get_backend() is (portable if location == "absent" else powerpoint)


def test_registry_access_error_stops_auto_selection(monkeypatch):
    def deny_access():
        raise PermissionError("access denied")

    monkeypatch.setattr(pptx, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(powerpoint, "is_installed", deny_access)
    monkeypatch.setattr(pptx, "find_spec", lambda name: pytest.fail("Unexpected portable fallback"))
    with pytest.raises(OSError, match="PowerPoint.*access denied"):
        pptx.get_backend()


@pytest.mark.parametrize("selected", [powerpoint, portable], ids=["powerpoint", "portable"])
@pytest.mark.parametrize("explicit", [True, False], ids=["explicit", "automatic"])
def test_installed_backend_failure_stops_and_keeps_output(monkeypatch, tmp_path, selected, explicit):
    monkeypatch.setattr(pptx, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(powerpoint, "is_installed", lambda: explicit or selected is powerpoint)
    monkeypatch.setattr(pptx, "find_spec", lambda name: object())
    cause = FileNotFoundError("转换所需资源不可读")
    calls = []

    def fail(*args):
        calls.append(selected.NAME)
        raise cause

    monkeypatch.setattr(selected, "stage_svg", fail)
    other = portable if selected is powerpoint else powerpoint
    monkeypatch.setattr(other, "stage_svg", lambda *args: pytest.fail("Unexpected backend fallback"))
    out = tmp_path / "previous.pptx"
    out.write_bytes(b"previous")
    with pytest.raises(pptx.BackendError) as failure:
        svg2pptx(b'<svg xmlns="http://www.w3.org/2000/svg" width="2in" height="1in"/>',
                 save=out, backend=selected.NAME if explicit else None)
    assert selected.NAME in str(failure.value) and "已安装" in str(failure.value)
    assert str(cause) in str(failure.value) and failure.value.__cause__ is cause
    assert calls == [selected.NAME] and out.read_bytes() == b"previous"


def test_unknown_backend_fails_before_probing_or_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(pptx, "find_spec", lambda *args: pytest.fail("Unexpected dependency probe"))
    monkeypatch.setattr(powerpoint, "is_installed", lambda: pytest.fail("Unexpected Office probe"))
    out = tmp_path / "result.pptx"
    with pytest.raises(ValueError, match="mystery.*powerpoint.*portable"):
        svg2pptx(SVG, out, backend="mystery")
    assert not out.exists()


@pytest.fixture
def conversion_stub(monkeypatch):
    # Isolate public file/stream semantics; the demo tests use real PowerPoint.
    def convert(source, target, stats, backend):
        assert read_svg(source).tag == qname("s:svg")
        Path(target).write_bytes(b"presentation")

    monkeypatch.setattr(api, "_write_pptx", convert)


def test_default_output_path(tmp_path, conversion_stub):
    source = tmp_path / "example.svg"
    source.write_bytes(SVG)
    target = svg2pptx(str(source))
    assert target == tmp_path / "example.pptx"
    assert target.read_bytes() == b"presentation" and source.read_bytes() == SVG


def test_bytes_return_and_stream_cursor(conversion_stub):
    source = BytesIO(SVG)
    source.seek(3)
    assert svg2pptx(source) == b"presentation"
    assert source.tell() == 3
    target = BytesIO(b"x" * 30)
    assert svg2pptx(SVG, save=target) is target
    assert target.tell() == 0 and target.read() == b"presentation"


def test_failure_preserves_supplied_stream(monkeypatch):
    def fail(source, dest, stats, backend):
        raise ValueError("invalid figure")
    monkeypatch.setattr(api, "_write_pptx", fail)
    target = BytesIO(b"previous result")
    with pytest.raises(ValueError, match="invalid figure"):
        svg2pptx(b"bad", save=target)
    assert target.getvalue() == b"previous result"


def test_reject_invalid_destinations(tmp_path):
    stream = BytesIO(b"<svg/>")
    with pytest.raises(ValueError):
        svg2pptx(stream, save=stream)
    with pytest.raises(ValueError):
        svg2pptx(stream, save=tmp_path / "out.svg")


def test_file_and_memory_details(tmp_path, conversion_stub):
    source = tmp_path / "source.svg"
    source.write_bytes(SVG)
    out = tmp_path / "custom.pptx"
    assert svg2pptx(source, save=out, version="2024") == out
    report = svg2pptx(source, save=out, return_details=True)
    assert report["output"] == out and report["version"] == "2024"
    assert svg2pptx(SVG, return_details=True)["output"] == b"presentation"
    buffer = BytesIO()
    assert svg2pptx(SVG, save=buffer, return_details=True)["output"] is buffer
    assert buffer.tell() == 0 and buffer.read() == b"presentation"


def test_unsupported_version_fails_before_writing(tmp_path):
    out = tmp_path / "original.pptx"
    out.write_bytes(b"keep")
    with pytest.raises(ValueError, match="2019.*2024"):
        svg2pptx(b"invalid", save=out, version="2019")
    assert out.read_bytes() == b"keep"


def test_failed_parse_restores_input_cursor():
    buf = BytesIO(b"<")
    buf.seek(1)
    with pytest.raises(ET.XMLSyntaxError):
        read_svg(buf)
    assert buf.tell() == 1


@pytest.mark.parametrize("choice", [None, "powerpoint", "portable"])
def test_figure_delegates_via_rewound_in_memory_svg(tmp_path, monkeypatch, choice):
    fig = Figure(figsize=(2, 1))
    fig.text(.1, .3, "in memory")
    path = tmp_path / "explicit.pptx"
    sentinel = {"output": path}

    def spy(source, *, save, version, backend, return_details):
        assert isinstance(source, BytesIO) and source.tell() == 0
        assert read_svg(source).get("width") == "144pt"
        assert (save, version, backend, return_details) == (path, "2024", choice, True)
        return sentinel

    monkeypatch.setattr(api, "svg2pptx", spy)
    monkeypatch.chdir(tmp_path)
    assert save_pptx(fig, path, version="2024", backend=choice, return_details=True) is sentinel
    assert not list(tmp_path.iterdir())

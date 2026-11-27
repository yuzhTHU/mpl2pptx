"""Public Python API and binary stream behaviour."""

from io import BytesIO
from pathlib import Path

from lxml import etree as ET
from matplotlib.figure import Figure
import pytest

from mpl2pptx import api, save_pptx, svg2pptx
from mpl2pptx.namespaces import qname
from mpl2pptx.svg.document import read_svg


SVG = b'<svg xmlns="http://www.w3.org/2000/svg"/>'


@pytest.fixture
def conversion_stub(monkeypatch):
    # Isolate public file/stream semantics; the demo tests use real PowerPoint.
    def convert(source, target, stats):
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
    def fail(source, dest, stats):
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


def test_figure_delegates_via_rewound_in_memory_svg(tmp_path, monkeypatch):
    fig = Figure(figsize=(2, 1))
    fig.text(.1, .3, "in memory")
    path = tmp_path / "explicit.pptx"
    sentinel = {"output": path}

    def spy(source, *, save, version, return_details):
        assert isinstance(source, BytesIO) and source.tell() == 0
        assert read_svg(source).get("width") == "144pt"
        assert (save, version, return_details) == (path, "2024", True)
        return sentinel

    monkeypatch.setattr(api, "svg2pptx", spy)
    monkeypatch.chdir(tmp_path)
    assert save_pptx(fig, path, version="2024", return_details=True) is sentinel
    assert not list(tmp_path.iterdir())

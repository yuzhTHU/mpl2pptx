"""Recover editable properties from SVG input."""

from collections import Counter
from io import BytesIO

from lxml import etree as ET
import matplotlib as mpl
from matplotlib.figure import Figure
import pytest

from mpl2pptx.namespaces import NS
from mpl2pptx.svg import text as svg_text
from mpl2pptx.svg.prepare import Dash, Hatch, prepare_svg
from mpl2pptx.svg.text import Label


def svg(content, defs=""):
    return ET.fromstring(f'<svg xmlns="{NS["s"]}" width="144pt" height="72pt" viewBox="0 0 144 72">'
                         f'<defs>{defs}</defs>{content}</svg>')


def test_svg_font_shorthand_and_alignment():
    root = svg('''<g><text style="font: italic 700 14px 'DejaVu Sans'; text-anchor:end"
                   x="100" y="20" fill="#123456">Reading</text></g>''')
    _, _, slots = prepare_svg(root)
    label, = slots.values()
    assert isinstance(label, Label)
    assert (label.content.source, label.family, label.size) == ("Reading", "DejaVu Sans", 14)
    assert label.bold and label.italic and label.align == "r" and label.color == "123456"


@pytest.mark.parametrize("fonttype", ["path", "none"])
def test_mixed_runs_and_literal_dollars(fonttype, monkeypatch):
    # Isolate SVG recovery here. The public conversion tests exercise real Office Math.
    monkeypatch.setattr(svg_text, "office_equation", lambda *args: ET.Element(f'{{{NS["m"]}}}oMath'))
    cases = [
        (r"$\frac{a}{b}$ with $c$", True, ("", r"\frac{a}{b}", " with ", "c", "")),
        (r"$x$ costs \$5", True, ("", "x", " costs $5")),
        ("$a$$b$", True, ("", "a", "", "b", "")),
        ("Office $a^2$ filing", False, ("Office $a^2$ filing",)),
        (r"Prices \$5 and \$7", True, ("Prices $5 and $7",)),
        ("Pay $2 or $3 or $4", True, ("Pay $2 or $3 or $4",)),
    ]
    figure = Figure(figsize=(5, 3))
    for i, (source, parse_math, _) in enumerate(cases):
        figure.text(.05, .1 + i / 8, source, parse_math=parse_math, family="DejaVu Sans", weight="bold")
    buffer = BytesIO()
    with mpl.rc_context({"svg.fonttype": fonttype}):
        figure.savefig(buffer, format="svg")
    detected = Counter()
    _, _, slots = prepare_svg(ET.fromstring(buffer.getvalue()), detected=detected)
    assert [label.content.parts for label in slots.values()] == [parts for _, _, parts in cases]
    assert detected == {"text": 5, "equations": 5}
    assert all(label.family == "DejaVu Sans" and label.bold for label in slots.values() if label.content.has_text)


@pytest.mark.parametrize("fonttype", ["path", "none"])
def test_failed_inline_formula_keeps_entire_source_line(fonttype, monkeypatch):
    def convert(latex, *args):
        if latex == "y":
            raise ValueError("unsupported formula")
        return ET.Element(f'{{{NS["m"]}}}oMath')

    monkeypatch.setattr(svg_text, "office_equation", convert)
    fig = Figure(figsize=(3, 1))
    fig.text(.1, .5, r"Compare $x$ and $y$")
    buf = BytesIO()
    with mpl.rc_context({"svg.fonttype": fonttype}):
        fig.savefig(buf, format="svg")
    root = ET.fromstring(buf.getvalue())
    group = root.xpath("//*[@id='text_1']")[0]
    original = ET.tostring(group)
    detected = Counter()
    with pytest.warns(UserWarning, match="unsupported formula"):
        _, _, slots = prepare_svg(root, detected=detected)
    assert not slots and ET.tostring(group) == original
    assert detected == {"text": 1, "equations": 2}


@pytest.mark.parametrize(("code", "preset"), [
    ("/", "upDiag"), ("\\", "dnDiag"), ("|", "vert"), ("-", "horz"), ("+", "cross"), ("x", "diagCross"),
])
def test_matplotlib_pattern_directions(code, preset):
    fig = Figure(figsize=(2, 2))
    ax = fig.subplots()
    ax.set_axis_off()
    ax.bar([0], [1], hatch=code, facecolor="#EEF4FF", edgecolor="#203355")
    buf = BytesIO()
    fig.savefig(buf, format="svg")
    root = ET.fromstring(buf.getvalue())
    hatch, = (v for v in prepare_svg(root)[2].values() if isinstance(v, Hatch))
    assert (hatch.preset, hatch.foreground, hatch.background) == (preset, ("203355", 1), ("EEF4FF", 1))


def test_odd_dash_array_and_reserved_color():
    root = svg('<path d="M0 0 L80 40" stroke="#c41379" fill="none" stroke-width="2" stroke-dasharray="4 1 2"/>')
    _, _, slots = prepare_svg(root)
    key, = slots
    assert key != "C41379"
    assert slots[key] == Dash("C41379", (2.0, 0.5, 1.0, 2.0, 0.5, 1.0))


@pytest.mark.parametrize(("source", "fonttype"), [
    ("Calibration", "path"), ("Equation: $a^2$", "path"), ("Equation: $a^2$", "none"),
])
def test_label_without_source_comment_preserves_glyphs(source, fonttype):
    fig = Figure(figsize=(2, 2))
    fig.text(.5, .5, source)
    buf = BytesIO()
    with mpl.rc_context({"svg.fonttype": fonttype}):
        fig.savefig(buf, format="svg")
    root = ET.fromstring(buf.getvalue(), ET.XMLParser(remove_comments=True))
    group = root.xpath("//*[@id='text_1']")[0]
    before = ET.tostring(group)
    with pytest.warns(UserWarning, match="Matplotlib"):
        _, _, slots = prepare_svg(root)
    assert not slots and ET.tostring(group) == before


def test_report_detects_unsupported_hatch_before_preparation():
    fig = Figure(figsize=(2, 2))
    ax = fig.subplots()
    ax.set_axis_off()
    ax.bar([0, 1], [1, 1], hatch="o")
    buf = BytesIO()
    fig.savefig(buf, format="svg")
    detected = Counter()
    with pytest.warns(UserWarning, match="填充图案"):
        _, _, slots = prepare_svg(ET.fromstring(buf.getvalue()), detected=detected)
    assert detected == {"hatches": 2}
    assert not any(isinstance(v, Hatch) for v in slots.values())

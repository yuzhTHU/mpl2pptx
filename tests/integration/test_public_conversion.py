"""Verify the public Figure and SVG entry points against the delivered slide XML."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree as ET
import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.figure import Figure
import pytest

from mpl2pptx import save_pptx, svg2pptx
from mpl2pptx.namespaces import NS
from mpl2pptx.pptx import get_backend, missing_portable_dependencies, powerpoint


@pytest.mark.integration
@pytest.mark.skipif(bool(missing_portable_dependencies()), reason="Requires the portable extra")
def test_portable_skips_svg_effects_without_calling_office(monkeypatch):
    def unexpected_office(*args):
        pytest.fail("portable called desktop PowerPoint")

    for name in ("is_installed", "stage_svg", "mathml_to_omml"):
        monkeypatch.setattr(powerpoint, name, unexpected_office)
    fig = Figure(figsize=(3, 2))
    fig.text(.1, .5, r"Area: $r^2$")
    with BytesIO() as buf:
        fig.savefig(buf, format="svg")
        svg = ET.fromstring(buf.getvalue())
    svg.append(ET.fromstring(f'<g xmlns="{NS["s"]}"><defs><filter id="blur"><feGaussianBlur '
                             'stdDeviation="2"/></filter></defs><rect width="12" height="12" '
                             'filter="url(#blur)"/><image href="external.png" width="20" height="20"/></g>'))
    with pytest.warns(UserWarning, match="portable") as messages:
        details = svg2pptx(ET.tostring(svg), backend="portable", return_details=True)
    warnings = " ".join(str(w.message) for w in messages)
    assert "filter" in warnings and "external or unreadable image" in warnings
    assert details["backend"] == "portable" and details["pictures"] == 0
    with ZipFile(BytesIO(details["output"])) as deck:
        slide = ET.fromstring(deck.read("ppt/slides/slide1.xml"))
    assert slide.xpath("//a:r/a:t/text()", namespaces=NS) == ["Area: "]
    assert slide.find(".//a14:m/m:oMath/m:sSup", NS) is not None


@pytest.mark.integration
@pytest.mark.parametrize("backend", [pytest.param("powerpoint", marks=pytest.mark.office), "portable"])
@pytest.mark.parametrize("entry_point", ["figure", "svg"])
@pytest.mark.parametrize("fonttype", ["path", "none"])
def test_public_conversion_report(tmp_path, backend, entry_point, fonttype):
    try:
        get_backend(backend)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    fig = Figure(figsize=(4, 3))
    ax = fig.subplots()
    ax.set_axis_off()
    ax.imshow([[0, 1], [1, 0]], extent=(0, 2, 0, 1))
    ax.bar([.4], [.6], width=.3, facecolor="white", edgecolor="navy", hatch="//")
    ax.plot([0, 2], [0, 1], color="orange", ls="--")
    fig.text(.05, .92, "Sample")
    fig.text(.4, .92, r"$x^2$")
    caption = r"Equation: $a^2$ and $\frac{b}{c}$ for \$5"
    family = "Arial Narrow" if "Arial Narrow" in font_manager.get_font_names() else "DejaVu Sans"
    fig.text(.05, .09, caption, fontfamily=family, fontweight="bold",
             fontstyle="italic", fontsize=11, color="#335577", alpha=.7, rotation=8)
    out = tmp_path / "result.pptx"

    with mpl.rc_context({"svg.fonttype": fonttype}):
        if entry_point == "figure":
            with mpl.rc_context({"svg.image_inline": False}):
                details = save_pptx(fig, out, version="2024", backend=backend, return_details=True)
                assert not mpl.rcParams["svg.image_inline"]
            assert {p.name for p in tmp_path.iterdir()} == {"result.pptx"}
        else:
            svg = tmp_path / "source.svg"
            fig.savefig(svg)
            details = svg2pptx(svg, save=out, version="2024", backend=backend, return_details=True)

    assert details["backend"] == backend and details["output"] == out and details["figures"] == 1
    assert details["elements"] == {
        "text": {"detected": 2, "converted": 2},
        "equations": {"detected": 3, "converted": 3},
        "hatches": {"detected": 1, "converted": 1},
        "dashes": {"detected": 1, "converted": 1},
    }
    assert (details["detected"], details["converted"], details["unconverted"]) == (7, 7, 0)
    with ZipFile(out) as z:
        slide = ET.fromstring(z.read("ppt/slides/slide1.xml"))
        page = ET.fromstring(z.read("ppt/presentation.xml")).find("p:sldSz", NS)
    assert (int(page.get("cx")), int(page.get("cy"))) == (4 * 914400, 3 * 914400)
    assert len(slide.findall(".//p:pic", NS)) == details["pictures"] == 1
    assert len(slide.xpath("//p:sp|//p:cxnSp", namespaces=NS)) == details["shapes"]
    box, = slide.xpath("//p:sp[p:nvSpPr/p:cNvPr[@name=$name]]", namespaces=NS, name=caption)
    assert box.find("p:spPr/a:xfrm", NS).get("rot") == str((360 - 8) * 60000)
    para, = box.findall("p:txBody/a:p", NS)
    runs = para.xpath("a:r|a14:m", namespaces=NS)
    assert [ET.QName(run).localname for run in runs] == ["r", "m", "r", "m", "r"]
    assert para.xpath("a:r/a:t/text()", namespaces=NS) == ["Equation: ", " and ", " for $5"]
    for run in runs[::2]:
        props = run.find("a:rPr", NS)
        assert (props.get("sz"), props.get("b"), props.get("i")) == ("1100", "1", "1")
        assert props.find("a:latin", NS).get("typeface") == family
        color = props.find("a:solidFill/a:srgbClr", NS)
        assert (color.get("val"), color.find("a:alpha", NS).get("val")) == ("335577", "70000")
    assert runs[1].xpath("m:oMath/m:sSup/m:sup//m:t/text()", namespaces=NS) == ["2"]
    assert runs[3].find("m:oMath/m:f", NS) is not None
    assert slide.xpath("//a:r/a:t/text()", namespaces=NS) == ["Sample", "Equation: ", " and ", " for $5"]
    for path in ("m:oMathPara/m:oMath/m:sSup", "a:pattFill", "a:custDash"):
        assert len(slide.findall(".//" + path, NS)) == 1


def test_plain_svg_bytes_report(tmp_path, conversion_output):
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="2in" height="1in" viewBox="0 0 192 96">
      <rect x="10" y="10" width="70" height="60" fill="#ffffff" stroke="#000000"
            stroke-width="1" stroke-dasharray="3 1"/>
      <text x="12" y="30" font-family="Arial" font-size="12">Trial</text>
    </svg>'''
    result = svg2pptx(svg, save=tmp_path / "result.pptx", return_details=True)
    assert result["figures"] == 1 and result["pictures"] == 0 and result["shapes"] == 2
    assert result["detected"] == result["converted"] == 2 and result["unconverted"] == 0
    assert result["elements"]["text"] == {"detected": 1, "converted": 1}
    assert result["elements"]["dashes"] == {"detected": 1, "converted": 1}


def test_native_radicals_and_integral(tmp_path, conversion_output):
    fig = Figure(figsize=(6, 2))
    fig.text(.05, .55, r"Compare $\sqrt{a}$, $\sqrt[3]{b}$ and $\int_0^1\frac{1}{1+x^5}\,dx$")
    out = tmp_path / "calculus.pptx"
    details = save_pptx(fig, out, return_details=True)
    assert details["elements"]["equations"] == {"detected": 3, "converted": 3}
    with ZipFile(out) as deck:
        slide = ET.fromstring(deck.read("ppt/slides/slide1.xml"))
    sqrt, root, integral = slide.findall(".//a14:m/m:oMath", NS)
    assert sqrt.find(".//m:rad/m:deg", NS) is not None
    assert root.xpath(".//m:rad/m:deg//m:t/text()", namespaces=NS) == ["3"]
    op, = integral.findall(".//m:nary", NS)
    assert op.xpath("m:sub//m:t/text()", namespaces=NS) == ["0"]
    assert op.xpath("m:sup//m:t/text()", namespaces=NS) == ["1"]
    assert integral.find(".//m:f", NS) is not None

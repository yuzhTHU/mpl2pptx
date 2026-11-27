"""Shared export and independent DrawingML checks for the runnable examples."""

import argparse
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET
import matplotlib as mpl
from matplotlib import pyplot as plt

from mpl2pptx import svg2pptx


NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "s": "http://www.w3.org/2000/svg",
    "xlink": "http://www.w3.org/1999/xlink",
}


@dataclass
class Drawing:
    svg: ET._Element
    group: ET._Element
    media: dict[str, bytes]

    def find(self, xpath, **variables):
        return self.group.xpath(xpath, namespaces=NS, **variables)

    def text(self, value):
        hits = self.find(".//p:sp[p:txBody/a:p/a:r/a:t=$value]", value=value)
        assert len(hits) == 1, f"Expected one editable text box for {value!r}, found {len(hits)}"
        return hits[0]

    def filled(self, rgb):
        return self.find(".//p:sp[p:spPr/a:solidFill/a:srgbClr/@val=$rgb]", rgb=rgb.removeprefix("#").upper())

    def stroked(self, rgb):
        return self.find(".//p:sp[p:spPr/a:ln/a:solidFill/a:srgbClr/@val=$rgb]", rgb=rgb.removeprefix("#").upper())


def run_demo(name, make_figure, check, output_dir=None, *, fonttype="none"):
    # The batch runner only saves files; make_figure() remains usable interactively.
    mpl.use("Agg")
    with mpl.rc_context():
        mpl.rcdefaults()
        mpl.rcParams.update({"font.family": "Arial", "font.size": 10, "axes.labelsize": 11,
                             "axes.titlesize": 14, "svg.fonttype": fonttype, "svg.hashsalt": name})
        fig = make_figure()
        png = BytesIO()
        svg = BytesIO()
        try:
            fig.savefig(png, format="png", transparent=True, metadata={"Date": None})
            fig.savefig(svg, format="svg", transparent=True, metadata={"Date": None})
        finally:
            plt.close(fig)
    if output_dir is None:
        deck = BytesIO(svg2pptx(svg))
    else:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        svg_source = folder / (name + ".svg")
        svg_source.write_bytes(svg.getvalue())
        png_source = (folder / (name + ".png"))
        png_source.write_bytes(png.getvalue())
        deck = svg2pptx(svg_source)
    root = ET.fromstring(svg.getvalue())
    with ZipFile(deck) as parts:
        assert parts.testzip() is None
        slide = ET.fromstring(parts.read("ppt/slides/slide1.xml"))
        pres = ET.fromstring(parts.read("ppt/presentation.xml"))
        media = {p: parts.read(p) for p in parts.namelist() if p.startswith("ppt/media/")}
    group, = slide.findall("p:cSld/p:spTree/p:grpSp", NS)
    expected = tuple(round(Decimal(root.get(attr).removesuffix("pt")) * 12700)
                     for attr in ("width", "height"))
    page = pres.find("p:sldSz", NS)
    extent = group.find("p:grpSpPr/a:xfrm/a:ext", NS)
    assert tuple(int(page.get(k)) for k in ("cx", "cy")) == expected
    assert tuple(int(extent.get(k)) for k in ("cx", "cy")) == expected
    assert group.find("p:grpSpPr/a:xfrm/a:off", NS).attrib == {"x": "0", "y": "0"}
    assert group.find(".//a:r/a:t", NS) is not None
    check(Drawing(root, group, media))
    return deck


def demo_cli(name, make_figure, check, *, fonttype="none"):
    parser = argparse.ArgumentParser(description=make_figure.__doc__)
    parser.add_argument("--output-dir", type=Path, help="Directory for the SVG and editable PPTX")
    options = parser.parse_args()
    output = run_demo(name, make_figure, check, options.output_dir, fonttype=fonttype)
    print(f"{name} passed" if options.output_dir is None else f"Verified {output}")

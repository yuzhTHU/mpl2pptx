"""DrawingML restoration and PPTX archive writes."""

from zipfile import ZipFile

from lxml import etree as ET

from mpl2pptx.namespaces import child, qname
from mpl2pptx.pptx.powerpoint import restore_editable_shapes
from mpl2pptx.pptx.writer import solid, write_package
from mpl2pptx.report import ConversionStats
from mpl2pptx.svg.prepare import Dash, Hatch


def test_zip_copy_can_reuse_open_source(tmp_path):
    source = tmp_path/"source.pptx"
    presentation = ET.Element(qname("p:presentation"))
    child(presentation, "p:sldSz", cx=914400, cy=914400)
    with ZipFile(source, "w") as z:
        z.writestr("ppt/presentation.xml", ET.tostring(presentation))
        z.writestr("part1", b"1")
        z.writestr("part2", b"2")
    with ZipFile(source) as z:
        for i in range(2):
            out = tmp_path/f"output{i}.pptx"
            write_package(z, out, {"part1": b"a much longer part"}, page_size=(914400, 914400))
            assert z.read("part2") == b"2"
            with ZipFile(out) as result:
                assert result.read("part1") == b"a much longer part"
                assert result.testzip() is None


def test_converted_styles_count_distinct_source_properties(tmp_path):
    # SVGEdit expanded the first style into two shapes and discarded the clipped second style.
    slide = ET.Element(qname("p:sld"))
    tree = child(child(slide, "p:cSld"), "p:spTree")
    for i in (1, 2):
        shape = child(tree, "p:sp")
        child(child(shape, "p:nvSpPr"), "p:cNvPr", id=i, name=f"part{i}")
        prop = child(shape, "p:spPr")
        solid(prop, "C40001")
        solid(child(prop, "a:ln", w=12700), "C40002")
    pres = ET.Element(qname("p:presentation"))
    child(pres, "p:sldSz", cx=914400, cy=914400)
    stage = tmp_path / "stage.pptx"
    with ZipFile(stage, "w") as parts:
        parts.writestr("ppt/slides/slide1.xml", ET.tostring(slide))
        parts.writestr("ppt/presentation.xml", ET.tostring(pres))
    hatch = Hatch("upDiag", ("000000", 1), ("FFFFFF", 1))
    dash = Dash("666666", (3, 1))
    slots = {"C40001": hatch, "C40002": dash, "C40003": hatch, "C40004": dash}
    stats = ConversionStats()
    stats.detected.update(hatches=2, dashes=2)
    out = tmp_path / "out.pptx"
    restore_editable_shapes(stage, out, (914400, 914400), slots, stats)
    with ZipFile(out) as parts:
        saved = ET.fromstring(parts.read("ppt/slides/slide1.xml"))
    assert len(saved.findall(".//{*}pattFill")) == len(saved.findall(".//{*}custDash")) == 2
    assert stats.converted == {"hatches": 1, "dashes": 1}
    assert stats.details(out, "2024")["unconverted"] == 2

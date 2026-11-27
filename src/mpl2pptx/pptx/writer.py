"""Write DrawingML shapes and apply slide changes to a PPTX archive atomically."""

import os
import tempfile
from copy import copy
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET

from ..namespaces import NS, child, qname


EMU_PER_PT = 12700


def solid(parent, rgb, opacity=1.0):
    add_color(child(parent, "a:solidFill"), rgb, opacity)


def add_color(parent, rgb, opacity):
    color = child(parent, "a:srgbClr", val=rgb.removeprefix("#").upper())
    if opacity != 1:
        child(color, "a:alpha", val=round(opacity * 100000))


def drawing_group(object_id, cx, cy):
    group = ET.Element(qname("p:grpSp"))
    nv = child(group, "p:nvGrpSpPr")
    child(nv, "p:cNvPr", id=object_id, name="Matplotlib figure")
    child(nv, "p:cNvGrpSpPr")
    child(nv, "p:nvPr")
    gxf = child(child(group, "p:grpSpPr"), "a:xfrm")
    child(gxf, "a:off", x=0, y=0)
    child(gxf, "a:ext", cx=cx, cy=cy)
    child(gxf, "a:chOff", x=0, y=0)
    child(gxf, "a:chExt", cx=cx, cy=cy)
    return group


def text_paragraph(group, object_id, name, frame, align, valign):
    sp = child(group, "p:sp")
    nv = child(sp, "p:nvSpPr")
    child(nv, "p:cNvPr", id=object_id, name=name)
    child(nv, "p:cNvSpPr", txBox=1)
    child(nv, "p:nvPr")
    prop = child(sp, "p:spPr")
    xf = child(prop, "a:xfrm")
    x, y, w, h = frame
    child(xf, "a:off", x=x, y=y)
    child(xf, "a:ext", cx=w, cy=h)
    child(child(prop, "a:prstGeom", prst="rect"), "a:avLst")
    child(prop, "a:noFill")
    body = child(sp, "p:txBody")
    body_pr = child(body, "a:bodyPr", wrap="none", lIns=0, tIns=0, rIns=0, bIns=0,
                    rtlCol=0, anchor=valign)
    child(body_pr, "a:spAutoFit")
    child(body, "a:lstStyle")
    para = child(body, "a:p")
    child(para, "a:pPr", algn=align)
    return para


def end_paragraph(para, family, hundredth_points, bold="0"):
    # The paragraph mark contributes to Office's line metrics even on a single line.
    end = child(para, "a:endParaRPr", lang="zh-CN", altLang="en-US", sz=hundredth_points, b=bold)
    child(end, "a:latin", typeface=family)
    child(end, "a:ea", typeface=family)
    child(end, "a:cs", typeface=family)


def write_text_run(para, text, label):
    if not text:
        return
    run = child(para, "a:r")
    style = child(run, "a:rPr", lang="en-US", altLang="zh-CN", sz=round(label.size * 100), b=int(label.bold))
    if label.italic:
        style.set("i", "1")
    solid(style, label.color, label.alpha)
    child(style, "a:latin", typeface=label.family)
    child(style, "a:ea", typeface=label.family)
    child(style, "a:cs", typeface=label.family)
    child(run, "a:t").text = text


def write_label(group, object_id, label):
    """Write a text box with its text runs and editable Office math zones in order."""
    parent = group
    if label.equations:
        alt = ET.SubElement(group, qname("mc:AlternateContent"), nsmap={k: NS[k] for k in ("mc", "a14", "m")})
        parent = child(alt, "mc:Choice", Requires="a14")
    frame = tuple(round(v * EMU_PER_PT) for v in label.frame)
    para = text_paragraph(parent, object_id, label.content.source, frame, label.align, label.valign)
    texts = label.content.parts[::2]
    write_text_run(para, texts[0], label)
    display_math = len(label.equations) == 1 and not label.content.has_text
    for equation, following_text in zip(label.equations, texts[1:]):
        zone = child(para, "a14:m")
        if display_math:
            zone = child(zone, "m:oMathPara")
            align = {"l": "left", "ctr": "centerGroup", "r": "right"}[label.align]
            child(child(zone, "m:oMathParaPr"), "m:jc").set(qname("m:val"), align)
        zone.append(equation)
        write_text_run(para, following_text, label)
    end_paragraph(para, "Arial" if display_math else label.family, round(label.size * 100), int(label.bold))


def write_package(archive, destination, changes, *, page_size):
    # PowerPoint's PageSetup COM setters quantize fractional points. The file
    # format supports whole EMUs, so store the SVG canvas at that precision.
    path = "ppt/presentation.xml"
    presentation = ET.fromstring(archive.read(path))
    size = presentation.find("p:sldSz", NS)
    size.set("cx", str(page_size[0]))
    size.set("cy", str(page_size[1]))
    size.set("type", "custom")
    changes = {**changes, path: ET.tostring(presentation, encoding="UTF-8", xml_declaration=True, standalone=True)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".pptx", delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        with ZipFile(temp_path, "w") as output:
            for info in archive.infolist():
                output.writestr(copy(info), changes[info.filename] if info.filename in changes else archive.read(info))
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)

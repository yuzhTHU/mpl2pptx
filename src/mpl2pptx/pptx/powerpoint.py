"""Import a prepared SVG in desktop PowerPoint, then restore its editable native objects."""

import os
import subprocess
from importlib.resources import files
from zipfile import ZipFile

from lxml import etree as ET

from ..namespaces import NS, child, qname
from ..svg.prepare import Dash, Hatch
from ..svg.text import Label
from .writer import add_color, drawing_group, write_label, write_package


def stage_svg(svg_path, stage, w, h):
    """Convert the SVG to shapes in desktop PowerPoint and ungroup them."""
    env = dict(os.environ, MPL_FIGURE_SVG=str(svg_path.resolve()), MPL_FIGURE_STAGE=str(stage),
               MPL_SLIDE_W=str(w), MPL_SLIDE_H=str(h))
    script = files(__package__).joinpath("stage_svg.ps1").read_text(encoding="utf-8")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)


def restore_dash(obj, dashes):
    stroke = obj.find("p:spPr/a:ln/a:solidFill/a:srgbClr", NS)
    key = stroke.get("val", "").upper() if stroke is not None else None
    dash = dashes.get(key)
    if dash is None:
        return
    stroke.set("val", dash.rgb)
    solid_fill = stroke.getparent()
    line = solid_fill.getparent()
    pattern = ET.Element(qname("a:custDash"))
    for length, space in zip(dash.lengths[::2], dash.lengths[1::2]):
        child(pattern, "a:ds", d=round(length * 100000), sp=round(space * 100000))
    existing = line.xpath("a:custDash|a:prstDash", namespaces=NS)
    if existing:
        line.replace(existing[0], pattern)
    else:
        solid_fill.addnext(pattern)
    return key


def restore_hatch(fill, hatch):
    pattern = ET.Element(qname("a:pattFill"), prst=hatch.preset)
    alpha = fill.find("a:alpha", NS)
    opacity = int(alpha.get("val")) / 100000 if alpha is not None else 1
    for tag, (rgb, value) in (("a:fgClr", hatch.foreground), ("a:bgClr", hatch.background)):
        add_color(child(pattern, tag), rgb, opacity * value)
    solid_fill = fill.getparent()
    solid_fill.getparent().replace(solid_fill, pattern)


def restore_editable_shapes(stage, destination, page_size, slots, stats):
    """Restore editable SVG properties in the stacking order supplied by PowerPoint."""
    dashes = {key: item for key, item in slots.items() if isinstance(item, Dash)}
    labels = {key: item for key, item in slots.items() if isinstance(item, Label)}
    slide_path = "ppt/slides/slide1.xml"
    with ZipFile(stage) as archive:
        slide = ET.fromstring(archive.read(slide_path))
        tree = slide.find("p:cSld/p:spTree", NS)
        last_id = max(map(int, tree.xpath(".//p:cNvPr/@id", namespaces=NS)))
        group = drawing_group(last_id + 1, *page_size)
        recovered = set()
        objects = [n for n in tree if n.tag not in (qname("p:nvGrpSpPr"), qname("p:grpSpPr"), qname("p:extLst"))]
        if not objects:
            raise ValueError("PowerPoint 未能从 SVG 转出绘图对象。")
        tree.insert(tree.index(objects[0]), group)
        for obj in objects:
            dash_key = restore_dash(obj, dashes)
            if dash_key is not None:
                recovered.add(dash_key)
            fill = obj.find("p:spPr/a:solidFill/a:srgbClr", NS)
            key = fill.get("val", "").upper() if fill is not None and obj.tag == qname("p:sp") else None
            item = slots.get(key)
            if isinstance(item, Hatch):
                restore_hatch(fill, item)
                recovered.add(key)
            if key not in labels:
                group.append(obj)
                continue
            if key in recovered:
                raise ValueError(f"PowerPoint 返回了重复的临时文字定位颜色 {key}。")
            recovered.add(key)
            label = labels[key]
            object_id = obj.find("p:nvSpPr/p:cNvPr", NS).get("id")
            write_label(group, object_id, label)
            if label.angle:
                group[-1].find(".//a:xfrm", NS).set("rot", str(round(label.angle * 60000) % 21600000))
            tree.remove(obj)
        # Entirely clipped or invisible strokes/fills need no slide object.
        missing = [label.content.source for key, label in labels.items() if key not in recovered]
        if missing:
            raise ValueError("PowerPoint 未能保留以下文字的位置：" + ", ".join(missing))
        # A source style can expand into several shapes via SVG <use>. Count it once.
        for key in recovered:
            item = slots[key]
            if isinstance(item, Label):
                item.content.count_features(stats.converted)
            else:
                kind = "dashes" if isinstance(item, Dash) else "hatches"
                stats.converted[kind] += 1
        stats.record_group(group)
        xml = ET.tostring(slide, encoding="UTF-8", xml_declaration=True, standalone=True)
        write_package(archive, destination, {slide_path: xml}, page_size=page_size)

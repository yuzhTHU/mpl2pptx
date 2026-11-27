"""Restore native text, equations and marked styles in a staged slide."""

from zipfile import ZipFile

from lxml import etree as ET

from ..namespaces import NS, child, qname
from ..svg.prepare import Dash, Hatch
from ..svg.text import Label
from .writer import add_color, drawing_group, write_label, write_package


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
    """Restore editable SVG properties without changing the original stacking order."""
    dashes = {key: item for key, item in slots.items() if isinstance(item, Dash)}
    labels = {key: item for key, item in slots.items() if isinstance(item, Label)}
    slide_path = "ppt/slides/slide1.xml"
    with ZipFile(stage) as archive:
        slide = ET.fromstring(archive.read(slide_path))
        tree = slide.find("p:cSld/p:spTree", NS)
        last_id = max(map(int, tree.xpath(".//p:cNvPr/@id", namespaces=NS)))
        group = drawing_group(last_id + 1, *page_size)
        recovered = set()
        properties = {qname("p:nvGrpSpPr"), qname("p:grpSpPr"), qname("p:extLst")}
        # SVGEdit already ungroups. svgslide emits absolute leaf coordinates
        # inside identity groups (off == chOff and ext == chExt).
        for subgroup in reversed(tree.findall(".//p:grpSp", NS)):
            for obj in list(subgroup):
                if obj.tag not in properties:
                    subgroup.addprevious(obj)
            subgroup.getparent().remove(subgroup)
        objects = [n for n in tree if n.tag not in properties]
        if not objects:
            raise ValueError("未能从 SVG 转出绘图对象。")
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
                raise ValueError(f"转换结果中出现了重复的临时文字定位颜色 {key}。")
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
            raise ValueError("未能保留以下文字的位置：" + ", ".join(missing))
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

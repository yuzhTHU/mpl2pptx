"""Mark text, hatch fills and dashed strokes for restoration after PowerPoint imports the SVG."""

import math
import re
import warnings
from collections import Counter
from dataclasses import dataclass

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from lxml import etree as ET
from matplotlib import colors

from ..namespaces import SVG
from .document import NUMBER_PATTERN, figure_viewport, style_of
from .text import label_content, read_label


@dataclass(frozen=True)
class Hatch:
    preset: str
    foreground: tuple[str, float]
    background: tuple[str, float]


@dataclass(frozen=True)
class Dash:
    rgb: str
    lengths: tuple[float, ...]  # DrawingML measures dashes in multiples of the pen width.


def slot_colors(root):
    occupied = {code.decode().upper() for code in re.findall(rb"#([0-9a-fA-F]{6})\b", ET.tostring(root))}
    for code in range(0xC41379, 0x1000000):
        rgb = f"{code:06X}"
        if rgb not in occupied:
            yield rgb


def set_paint(node, prop, rgb):
    """Replace one presentation property without discarding other inline CSS."""
    node.set(prop, "#" + rgb)
    declarations = [p for p in node.get("style", "").split(";") if p.partition(":")[0].strip() != prop]
    node.set("style", ";".join(declarations))


def hatch_pattern(pattern):
    """Identify line directions from the tile geometry, independently of SVG IDs."""
    tile, path = pattern.find(SVG + "rect"), pattern.find(SVG + "path")
    if tile is None or path is None or len(pattern) != 2:
        return None
    pen = RecordingPen()
    parse_path(path.get("d"), pen)
    ops = pen.value
    directions = set()
    for i in range(0, len(ops), 3):
        segment = ops[i:i + 3]
        if [op for op, _ in segment] != ["moveTo", "lineTo", "endPath"]:
            return None
        (x0, y0), (x1, y1) = segment[0][1][0], segment[1][1][0]
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < 1e-8:
            directions.add("vertical")
        elif abs(dy) < 1e-8:
            directions.add("horizontal")
        elif math.isclose(abs(dx), abs(dy), rel_tol=1e-6):
            directions.add("up" if dx * dy < 0 else "down")
        else:
            return None
    presets = {("up",): "upDiag", ("down",): "dnDiag", ("horizontal",): "horz",
               ("vertical",): "vert", ("down", "up"): "diagCross", ("horizontal", "vertical"): "cross"}
    preset = presets.get(tuple(sorted(directions)))
    if preset is None:
        return None

    def paint(node, prop):
        style = style_of(node)
        value = style.get(prop, "black")
        if value == "none":
            return "FFFFFF", 0.0
        rgba = colors.to_rgba(value)
        alpha = rgba[3] * style["opacity"] * float(style.get(prop + "-opacity", 1))
        return colors.to_hex(rgba)[1:].upper(), alpha

    return Hatch(preset, paint(path, "stroke"), paint(tile, "fill"))


def mark_hatches(root, available, detected):
    patterns = {p.get("id"): p for p in root.iter(SVG + "pattern")}
    slots = {}
    if not patterns:
        return slots
    for el in root.xpath(".//*[@fill or contains(@style,'url(')]"):
        style = style_of(el)
        ref = re.fullmatch(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)", style.get("fill", ""))
        if not ref or ref[1] not in patterns:
            continue
        detected["hatches"] += 1
        hatch = hatch_pattern(patterns[ref[1]])
        if hatch is None:
            warnings.warn(f"PowerPoint 可能省略不支持的 SVG 填充图案 {ref[1]}", stacklevel=2)
            continue
        rgb = next(available)
        slots[rgb] = hatch
        set_paint(el, "fill", rgb)
    return slots


def mark_dashes(root, available, detected):
    slots = {}
    for el in root.xpath(".//*[@stroke-dasharray or contains(@style,'stroke-dasharray')]"):
        style = style_of(el)
        dash_array = style["stroke-dasharray"].strip()
        color = style.get("stroke", "none")
        if dash_array == "none" or color == "none":
            continue
        detected["dashes"] += 1
        values = re.split(r"[\s,]+", dash_array)
        width = str(style.get("stroke-width", "1")).removesuffix("px")
        if not all(re.fullmatch(NUMBER_PATTERN, v) for v in [width, *values]) or float(width) <= 0:
            continue
        if not colors.is_color_like(color):
            continue
        lengths = tuple(float(v) / float(width) for v in values)
        if min(lengths) < 0 or not any(lengths):
            continue
        if len(lengths) % 2:
            lengths *= 2
        rgb = next(available)
        slots[rgb] = Dash(colors.to_hex(color)[1:].upper(), lengths)
        set_paint(el, "stroke", rgb)
    return slots


def prepare_svg(root, canvas=None, *, mathml_to_omml, detected=None):
    """Mark slots in a temporary SVG, retaining geometry, clipping and stacking order."""
    w, h, viewport = canvas if canvas is not None else figure_viewport(root)
    available = slot_colors(root)
    if detected is None:
        detected = Counter()
    slots = mark_hatches(root, available, detected)
    slots.update(mark_dashes(root, available, detected))
    svg_ns = {"s": ET.QName(root).namespace}
    # Each line is either a plain <text> or a comment followed by a glyph group.
    # Include outline groups with missing comments to report that text cannot be recovered.
    nodes = root.xpath(".//s:text[not(*) and not(ancestor::s:defs)] | "
                       ".//s:g[(s:use or s:text/s:tspan) and "
                       "(preceding-sibling::node()[not(self::text())][1][self::comment()] or "
                       "starts-with(parent::s:g/@id, 'text_'))]", namespaces=svg_ns)
    for node in nodes:
        group = node.getparent()
        content = label_content(node)
        content.count_features(detected)
        try:
            label, x, y, local_size = read_label(node, viewport, content, mathml_to_omml)
        except (ValueError, KeyError) as exc:
            warnings.warn(f"{group.get('id', 'text')}: {exc}，保留 SVG 原有图形。", stacklevel=2)
            continue
        rgb = next(available)
        slots[rgb] = label
        # Glyph definitions in one label can be referenced by later labels.
        for defs in list(node.iter(SVG + "defs")):
            group.insert(0, defs)
        slot = ET.Element(SVG + "rect", x=str(x), y=str(y), width=str(local_size / 3),
                          height=str(local_size / 3), fill="#" + rgb, stroke="none")
        if node.get("transform"):
            slot.set("transform", node.get("transform"))
        group.replace(node, slot)

    # SVGEdit can discard a nonzero viewBox origin. Express the same viewport
    # with an explicit translation, so Office positions paths and text alike.
    root.set("width", f"{w:.15g}pt")
    root.set("height", f"{h:.15g}pt")
    root.set("viewBox", f"0 0 {w / viewport.xx:.15g} {h / viewport.yy:.15g}")
    root.set("preserveAspectRatio", "none")
    if viewport.dx or viewport.dy:
        tx, ty = viewport.dx / viewport.xx, viewport.dy / viewport.yy
        content = ET.Element(SVG + "g", transform=f"translate({tx:.15g} {ty:.15g})")
        definitions = {SVG + tag for tag in ("defs", "style", "metadata", "desc", "title", "symbol")}
        for el in list(root):
            if isinstance(el.tag, str) and el.tag not in definitions:
                content.append(el)
        root.append(content)
    return w, h, slots

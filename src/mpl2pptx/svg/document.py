"""Read SVG documents, resolve units and compose transforms and inherited styles."""

import math
import os
import re
from io import BytesIO

from fontTools.misc.transform import Identity, Transform
from lxml import etree as ET
from matplotlib import font_manager as fm

from ..namespaces import qname


NUMBER_PATTERN = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def read_svg(source):
    """Read a path, raw SVG bytes or a binary stream. Preserve the caller's cursor."""
    if isinstance(source, (str, os.PathLike)):
        source = os.fspath(source)
    elif isinstance(source, bytes):
        source = BytesIO(source)
    position = source.tell() if not isinstance(source, str) and source.seekable() else None
    try:
        if position is not None:
            source.seek(0)
        root = ET.parse(source, ET.XMLParser(resolve_entities=False, no_network=True)).getroot()
    finally:
        if position is not None:
            source.seek(position)
    if root.tag != qname("s:svg"):
        raise ValueError("输入文件的根元素须为 SVG。")
    return root


def figure_viewport(root):
    """Resolve the physical canvas (points) and the viewBox-to-canvas transform."""
    properties = dict((k.strip(), v.strip()) for k, v in
                      (p.split(":", 1) for p in root.get("style", "").split(";") if ":" in p))

    def points(name):
        value = properties.get(name, root.get(name, "auto")).strip().lower()
        if value == "auto":
            return None
        match = re.fullmatch(f"({NUMBER_PATTERN})(px|pt|in|cm|mm|pc|q)?", value)
        if not match:
            raise ValueError(f"独立 SVG 需要绝对画幅尺寸，无法将 {name}={value!r} 换算成磅。")
        factors = {"pt": 1, "px": 0.75, "in": 72, "cm": 72 / 2.54, "mm": 72 / 25.4,
                   "pc": 12, "q": 72 / 101.6}
        return float(match[1]) * factors[match[2] or "px"]

    w, h = points("width"), points("height")
    if any(v is not None and not (math.isfinite(v) and v > 0) for v in (w, h)):
        raise ValueError("SVG 画幅须为有限正数。")
    if "viewBox" not in root.attrib:
        if w is None or h is None:
            raise ValueError("请给 SVG 指定宽高或 viewBox，以确定页面尺寸。")
        return w, h, Identity.scale(0.75)  # 96 CSS pixels per inch
    x, y, vw, vh = map(float, root.get("viewBox").replace(",", " ").split())
    if not all(map(math.isfinite, (x, y, vw, vh))) or min(vw, vh) <= 0:
        raise ValueError("SVG 的 viewBox 须有有限坐标和正宽高。")
    if w is None:
        w = 0.75 * vw if h is None else h * vw / vh
    if h is None:
        h = w * vh / vw
    sx, sy = w / vw, h / vh
    aspect = root.get("preserveAspectRatio", "xMidYMid meet").strip().removeprefix("defer ").split()
    if aspect[:1] == ["none"]:
        transform = Identity.scale(sx, sy)
    else:
        align = re.fullmatch(r"x(Min|Mid|Max)Y(Min|Mid|Max)", aspect[0] if aspect else "xMidYMid")
        if not align or aspect[1:] not in ([], ["meet"], ["slice"]):
            raise ValueError("无法识别 SVG 的 preserveAspectRatio。")
        scale = max(sx, sy) if aspect[1:] == ["slice"] else min(sx, sy)
        offsets = {"Min": 0, "Mid": 0.5, "Max": 1}
        tx, ty = (w - vw * scale) * offsets[align[1]], (h - vh * scale) * offsets[align[2]]
        transform = Identity.translate(tx, ty).scale(scale)
    return w, h, transform.translate(-x, -y)


def transform_of(node, viewport):
    """Compose the SVG transforms in drawing order, including rotations about a point."""
    matrix = viewport
    for el in [*reversed(list(node.iterancestors())), node]:
        for cmd, raw in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", el.get("transform", "")):
            v = [float(n) for n in re.findall(NUMBER_PATTERN, raw)]
            if cmd == "translate":
                matrix = matrix.translate(*v)
            elif cmd == "scale":
                matrix = matrix.scale(*v)
            elif cmd == "rotate":
                cx, cy = v[1:] if len(v) == 3 else (0, 0)
                matrix = matrix.translate(cx, cy).rotate(math.radians(v[0])).translate(-cx, -cy)
            elif cmd == "matrix":
                matrix = matrix.transform(Transform(*v))
            else:
                raise ValueError(f"文字包含不支持的变换 {cmd}")
    return matrix


def style_of(node):
    style = {}
    opacity = 1.0
    for el in [*reversed(list(node.iterancestors())), node]:
        values = dict(el.attrib)
        values.update((k.strip(), v.strip()) for k, v in
                      (p.split(":", 1) for p in el.get("style", "").split(";") if ":" in p))
        opacity *= float(values.get("opacity", 1))
        for key, value in values.items():
            if key == "font":
                # Expand the CSS font shorthand into the properties used by text boxes.
                match = re.search(rf"(?<!\S)({NUMBER_PATTERN}(?:pt|px))(?:/\S+)?\s+(.+)$", value)
                if match:
                    flags = value[:match.start()].split()
                    style.update({"font-size": match[1], "font-family": match[2],
                                  "font-weight": next((s for s in flags if s.isdigit() or
                                                       s in fm.weight_dict and s != "normal"), "normal"),
                                  "font-style": next((s for s in flags if s in ("italic", "oblique")), "normal")})
            else:
                style[key] = value
    style["opacity"] = opacity
    return style

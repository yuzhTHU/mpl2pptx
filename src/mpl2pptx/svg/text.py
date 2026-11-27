"""Recover text, font metrics, alignment and math labels from Matplotlib SVG."""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import unquote
from xml.sax.saxutils import unescape

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont, TTLibError
from lxml import etree as ET
from matplotlib import colors, font_manager as fm
from matplotlib.textpath import TextToPath

from ..namespaces import SVG, XLINK_HREF
from ..pptx.equations import office_equation
from .document import NUMBER_PATTERN, style_of, transform_of


TEXT_PATH = TextToPath()


@dataclass
class LabelContent:
    source: str
    # Matplotlib mathtext alternates literal text and LaTeX, including empty end runs.
    parts: tuple[str, ...]

    @property
    def equation_count(self):
        return len(self.parts) // 2

    @property
    def has_text(self):
        return not self.equation_count or any(self.parts[::2])

    def count_features(self, counts):
        if self.has_text:
            counts["text"] += 1
        if self.equation_count:
            counts["equations"] += self.equation_count


@dataclass
class Label:
    content: LabelContent
    frame: tuple[float, float, float, float]  # slide points, before rotation
    size: float
    family: str
    bold: bool
    italic: bool
    color: str
    alpha: float
    align: str
    valign: str
    angle: float
    equations: tuple[ET._Element, ...]


def user_font_size(style):
    value = style.get("font-size", "")
    match = re.fullmatch(f"({NUMBER_PATTERN})(px|pt)?", value)
    if not match:
        raise ValueError(f"缺少明确的 SVG 字号 {value!r}")
    return float(match[1]) * (4 / 3 if match[2] == "pt" else 1)


@lru_cache(maxsize=256)
def outline_face(postscript_name):
    """Read the face and its dollar glyph index from the font named by Matplotlib."""
    def normal(s):
        return re.sub(r"[\W_]", "", s).casefold()

    ps = normal(postscript_name)
    entries = sorted(fm.fontManager.ttflist,
                     key=lambda e: len(normal(e.name)) if ps.startswith(normal(e.name)) else 0,
                     reverse=True)
    seen = set()
    for entry in entries:
        file = entry.fname
        face = getattr(file, "face_index", getattr(entry, "face_index", 0))
        key = (os.fspath(file), face)
        if key in seen:
            continue
        seen.add(key)
        try:
            with TTFont(key[0], fontNumber=face, lazy=True) as font:
                names = font["name"]
                if names.getDebugName(6) != postscript_name:
                    continue
                family = names.getDebugName(1) or entry.name
                face_style = family, font["OS/2"].usWeightClass >= 600, bool(font["OS/2"].fsSelection & 1)
                dollar = (font.getBestCmap() or {}).get(ord("$"))
                return face_style, font.getGlyphID(dollar) if dollar else None
        except (OSError, KeyError, TTLibError):
            continue
    raise ValueError(f"本机找不到轮廓使用的字体 {postscript_name}")


def inferred_alignment(group, viewport, left, baseline, width):
    """Outlined text retains its baseline origin but has no explicit text-anchor."""
    parent = group.getparent()
    if parent is None:
        return "l", "t"
    name = parent.get("id", "")
    if name.startswith(("xtick_", "ytick_")):
        tick = next((u for u in parent.iter(SVG + "use") if u.get("x") and u.get("y")), None)
        if tick is not None:
            x, y = transform_of(tick, viewport).transformPoint((float(tick.get("x")), float(tick.get("y"))))
            if name.startswith("xtick_"):
                return "ctr", "t" if baseline >= y else "b"
            return ("r" if left < x else "l"), "ctr"
    if name.startswith("axes_"):
        patch = next((p.find(SVG + "path") for p in parent.findall(SVG + "g")
                      if p.get("id", "").startswith("patch_")), None)
        if patch is not None:
            pen = BoundsPen(None)
            parse_path(patch.get("d"), pen)
            if pen.bounds:
                x0, y0, x1, _ = pen.bounds
                center, top = transform_of(patch, viewport).transformPoint(((x0 + x1) / 2, y0))
                if baseline <= top + 1 and abs(left + width / 2 - center) < 1.5:
                    return "ctr", "b"
    return "l", "t"


def glyph_ref(use):
    face, _, code = unquote(use.get(XLINK_HREF, "").lstrip("#")).rpartition("-")
    return face, code


def literal_outline(node, source):
    """Distinguish drawn dollar signs (e.g. parse_math=False) from math delimiters."""
    refs = [glyph_ref(use) for use in node.findall(SVG + "use")]
    if not refs:
        return False
    # Matplotlib SVGs can identify glyphs by code point or by font glyph index.
    if len(refs) == len(source) and all(code == f"{ord(char):x}" for (_, code), char in zip(refs, source)):
        return True
    # Plain text can contain ligatures, so count drawn dollars independently of glyph positions.
    dollars = source.count("$")
    for (face, code), count in Counter(refs).items():
        if count != dollars:
            continue
        try:
            _, dollar = outline_face(face)
            if int(code, 16) == dollar:
                return True
        except ValueError:
            continue
    return False


def label_content(node):
    """Read the rendered line and split only genuine Matplotlib mathtext."""
    if node.tag == SVG + "text":
        text = node.text or ""
        return LabelContent(text, (text,))
    comment = node.getprevious()
    source = unescape(comment.text.removeprefix(" ").removesuffix(" ")) if isinstance(comment, ET._Comment) else ""
    parts = re.split(r"(?<!\\)\$", source)
    if len(parts) < 3 or len(parts) % 2 == 0 or not all(parts[1::2]) or literal_outline(node, source):
        return LabelContent(source, (source,))
    parts[::2] = [text.replace(r"\$", "$") for text in parts[::2]]
    return LabelContent(source, tuple(parts))


def prose_glyph_index(content):
    """Locate an ordinary character even when the label starts and ends with math."""
    if content.parts[0]:
        return 0
    if content.parts[-1]:
        return -1
    offset = 0
    for latex, text in zip(content.parts[1::2], content.parts[2::2]):
        offset += len(TEXT_PATH.mathtext_parser.parse("$" + latex + "$").glyphs)
        if text:
            break
    return offset


def text_face(style):
    family = style.get("font-family", "sans-serif").split(",")[0].strip(" '\"")
    weight = style.get("font-weight", "400")
    bold = float(weight) >= 600 if weight.isdigit() else fm.weight_dict.get(weight, 400) >= 600
    italic = style.get("font-style") in ("italic", "oblique")
    stretch = style.get("font-stretch", "normal")
    if stretch != "normal":
        # Mathtext can emit Arial Narrow as 'Arial' with a condensed stretch.
        props = fm.FontProperties(family=[family], stretch=stretch, weight="bold" if bold else "normal",
                                  style=style.get("font-style", "normal"))
        try:
            path = fm.findfont(props, fallback_to_default=False)
            with TTFont(os.fspath(path), fontNumber=getattr(path, "face_index", 0), lazy=True) as font:
                family = font["name"].getDebugName(1) or family
        except (ValueError, OSError, KeyError, TTLibError):
            pass
    return family, bold, italic


def group_font(node, content):
    """Recover the base size and text face from the SVG glyphs for one rendered line."""
    spans = list(node.iter(SVG + "tspan"))
    if not content.has_text:
        size = max((user_font_size(style_of(s)) for s in spans), default=TEXT_PATH.FONT_SCALE)
        return ("Cambria Math", False, False), size
    uses = node.findall(SVG + "use")
    if content.equation_count:
        index = prose_glyph_index(content)
        try:
            if spans:
                # SVG groups tspans by style. A span may carry several x positions.
                positioned = [(float(x), span) for span in spans for x in re.findall(NUMBER_PATTERN, span.get("x", "0"))]
                positioned.sort(key=lambda pair: pair[0])
                prose_style = style_of(positioned[index][1])
                return text_face(prose_style), user_font_size(prose_style)
            face = glyph_ref(uses[index])[0]
        except IndexError as exc:
            raise ValueError("找不到混排文字的字形") from exc
    else:
        faces = {glyph_ref(u)[0] for u in uses}
        if len(faces) != 1:
            raise ValueError("轮廓包含多个字体，或缺少字形引用")
        face = faces.pop()
    return outline_face(face)[0], TEXT_PATH.FONT_SCALE


def read_label(node, viewport, content, mathml_to_omml):
    group = node.getparent()
    if not content.source:
        raise ValueError("没有文字节点或 Matplotlib 的原文注释")
    anchor = None
    x = y = 0.0
    style = style_of(node)
    if node.tag == SVG + "text":
        local_size = user_font_size(style)
        family, bold, italic = text_face(style)
        anchor = {"start": "l", "middle": "ctr", "end": "r"}[style.get("text-anchor", "start")]
        x, y = float(node.get("x", 0)), float(node.get("y", 0))
    else:
        (family, bold, italic), local_size = group_font(node, content)

    matrix = transform_of(node, viewport)
    a, b = matrix.transformVector((1, 0))
    c, d = matrix.transformVector((0, 1))
    scale = math.hypot(a, b)
    if not scale or not math.isclose(scale, math.hypot(c, d), rel_tol=1e-4) or abs(a*c + b*d) > 1e-4 * scale**2:
        raise ValueError("文字经过非等比缩放或斜切")
    size = local_size * scale
    theta = math.atan2(b, a)
    cos, sin = math.cos(theta), math.sin(theta)
    props = fm.FontProperties(family=family, size=size, weight="bold" if bold else "normal",
                              style="italic" if italic else "normal")
    width, ink_h, desc = TEXT_PATH.get_text_width_height_descent(content.source, props, ismath=bool(content.equation_count))
    bx, by = matrix.transformPoint((x, y))
    fraction = {"l": 0.0, "ctr": 0.5, "r": 1.0}.get(anchor, 0.0)
    bx, by = bx - width * fraction * cos, by - width * fraction * sin
    inferred, valign = inferred_alignment(group, viewport, bx, by, width)
    align = anchor or inferred
    # Invert the zero-inset, single-line Office box metrics used by the drawing script.
    ascent = max(size * .978, ink_h - desc)
    height = ascent + max(size * .234, desc)
    dx, dy = width / 2, height / 2 - ascent
    cx, cy = bx + dx*cos - dy*sin, by + dx*sin + dy*cos
    frame = (cx - width/2, cy - height/2, width, height)
    rgba = colors.to_rgba(style.get("fill", "black"))
    rgb = colors.to_hex(rgba)[1:].upper()
    alpha = style["opacity"] * float(style.get("fill-opacity", 1)) * rgba[3]
    equations = tuple(office_equation(latex, size, rgb, alpha, mathml_to_omml) for latex in content.parts[1::2])
    label = Label(content, frame, size, family, bold, italic, rgb, alpha,
                  align, valign, math.degrees(theta), equations)
    return label, x, y, local_size

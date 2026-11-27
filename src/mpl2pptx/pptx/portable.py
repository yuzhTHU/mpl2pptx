"""Headless SVG and Office Math conversion using the portable extra."""

import warnings
from collections import Counter

from lxml import etree as ET

from ..namespaces import NS, child, qname


NAME = "portable"


def stage_svg(svg, stage, w, h):
    from svgslide import convert

    # Scatter markers and vector heatmap cells must remain individually editable.
    report = convert(svg, stage, merge=None, canvas_size=(w, h))
    if report.skipped:
        counts = Counter(feature for feature, _ in report.skipped)
        skipped = ", ".join(f"{feature} ({n})" for feature, n in counts.items())
        warnings.warn(f"portable 模式未能完整保留以下 SVG 特性：{skipped}", stacklevel=2)


def mathml_to_omml(mathml):
    from mathml2omml import convert

    # latex2mathml wraps the whole expression in an unstyled mrow. Leaving
    # it in place adds an extra editable Office box around every equation.
    row_tag = "{http://www.w3.org/1998/Math/MathML}mrow"
    if len(mathml) == 1 and mathml[0].tag == row_tag and not mathml[0].attrib:
        row = mathml[0]
        mathml.remove(row)
        mathml.extend(list(row))
    try:
        fragment = convert(ET.tostring(mathml, encoding="unicode"))
        # The converter returns an OMML fragment with an unbound m: prefix.
        math = ET.fromstring(f'<root xmlns:m="{NS["m"]}">{fragment}</root>'.encode())[0]
    except (ValueError, RuntimeError, LookupError, ET.XMLSyntaxError) as exc:
        raise ValueError(f"无法将 MathML 转换为 Office 公式（{type(exc).__name__}）") from exc
    # Office requires a degree argument even when the square root hides it.
    for radical in math.xpath(".//m:rad[not(m:deg)]", namespaces=NS):
        properties = ET.Element(qname("m:radPr"))
        child(properties, "m:degHide").set(qname("m:val"), "1")
        radical.insert(0, properties)
        radical.insert(1, ET.Element(qname("m:deg")))
    return math

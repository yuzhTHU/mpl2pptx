"""Convert Matplotlib mathtext to native Office Math through MathML."""

import re

from lxml import etree as ET

from ..namespaces import DRAWINGML, OFFICE_MATH


def office_equation(latex, size, rgb, alpha, mathml_to_omml):
    from latex2mathml.converter import convert

    try:
        # LogFormatterMathtext wraps tick labels in this Matplotlib-only command.
        latex = re.sub(r"\\(?:mathdefault|mathregular)(?=\s*\{)", r"\\mathrm", latex)
        mathml = ET.fromstring(convert(latex).encode())
    except Exception as exc:
        raise ValueError(f"不能将这个数学表达式转为 MathML（{type(exc).__name__}）") from exc
    for identifier in mathml.iter("{http://www.w3.org/1998/Math/MathML}mi"):
        if re.fullmatch(r"\\[A-Za-z]+", identifier.text or ""):
            raise ValueError(f"不能将数学命令 {identifier.text} 转为 Office 公式")
    math = mathml_to_omml(mathml)
    if math is None or math.tag != OFFICE_MATH + "oMath" or math.find(".//" + OFFICE_MATH + "r/" + OFFICE_MATH + "t") is None:
        raise ValueError("Office 未能识别这个数学表达式。")
    for run in math.iter(OFFICE_MATH + "r"):
        token = run.find(OFFICE_MATH + "t")
        if token is None:
            continue
        props = ET.Element(DRAWINGML + "rPr", lang="en-US", sz=str(round(size * 100)))
        fill = ET.SubElement(ET.SubElement(props, DRAWINGML + "solidFill"), DRAWINGML + "srgbClr", val=rgb)
        if alpha != 1:
            ET.SubElement(fill, DRAWINGML + "alpha", val=str(round(alpha * 100000)))
        ET.SubElement(props, DRAWINGML + "latin", typeface="Cambria Math")
        token.addprevious(props)
    return math

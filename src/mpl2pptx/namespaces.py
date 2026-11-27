"""XML namespaces shared by the SVG reader and the PowerPoint writer."""

from lxml import etree as ET


NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "s": "http://www.w3.org/2000/svg",
    "xlink": "http://www.w3.org/1999/xlink",
}


def qname(name):
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


def child(parent, tag, **attrs):
    return ET.SubElement(parent, qname(tag), {k: str(v) for k, v in attrs.items()})


SVG = "{" + NS["s"] + "}"
DRAWINGML = "{" + NS["a"] + "}"
OFFICE_MATH = "{" + NS["m"] + "}"
XLINK_HREF = qname("xlink:href")

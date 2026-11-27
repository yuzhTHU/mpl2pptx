"""Count recognized SVG features and the native objects written into PowerPoint."""

from collections import Counter

from .namespaces import NS


ELEMENT_NAMES = {"text": "文字", "equations": "公式", "hatches": "图案填充", "dashes": "虚线"}


class ConversionStats:
    def __init__(self):
        self.detected = Counter()
        self.converted = Counter()
        self.figures = self.shapes = self.pictures = 0

    def record_group(self, group):
        """Count actual Office objects once, including editable equations in mc:Choice."""
        self.figures += 1
        self.shapes += int(group.xpath("count(.//p:sp[not(ancestor::mc:Fallback)] | "
                                       ".//p:cxnSp[not(ancestor::mc:Fallback)])", namespaces=NS))
        self.pictures += int(group.xpath("count(.//p:pic[not(ancestor::mc:Fallback)])", namespaces=NS))

    def details(self, output, version):
        elements = {kind: {"detected": self.detected[kind], "converted": self.converted[kind]}
                    for kind in ELEMENT_NAMES}
        detected, converted = sum(self.detected.values()), sum(self.converted.values())
        return {"output": output, "version": version, "figures": self.figures,
                "shapes": self.shapes, "pictures": self.pictures, "elements": elements,
                "detected": detected, "converted": converted, "unconverted": detected - converted}

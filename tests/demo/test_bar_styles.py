"""Matplotlib bar fills, outlines and independent opacity values."""

from demo_support import NS, demo_cli, run_demo


def make_figure():
    """Draw four bars with different fill and line treatments."""
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    fig, ax = plt.subplots(figsize=(6.4, 3.8), layout="constrained", dpi=300)
    ax.bar(
        "Outline", 63,
        facecolor="none",
        edgecolor="#304D63",
        linewidth=1.8
    )
    ax.bar(
        "Solid", 78,
        facecolor="#347E76",
        edgecolor="none"
    )
    ax.bar(
        "Tint", 57,
        facecolor=mcolors.to_rgba("#4784AD", 0.36),
        edgecolor=mcolors.to_rgba("#8D374D", 0.65),
        linewidth=1.8,
        linestyle="--"
    )
    ax.bar(
        "Hatch", 85,
        facecolor="#F4E8D3",
        edgecolor="#80572F",
        hatch="///",
        linewidth=1.2
    )
    ax.set_title("Coating coverage", fontsize=14, fontweight="bold")
    ax.set_xlabel("Finish", fontsize=11)
    ax.set_ylabel("Surface coverage (%)", fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#D7DEE0", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    
    return fig


def check(drawing):
    drawing.text("Coating coverage")
    outline, = drawing.stroked("304D63")
    assert outline.find("p:spPr/a:noFill", NS) is not None
    solid, = drawing.filled("347E76")
    assert solid.find("p:spPr/a:ln/a:noFill", NS) is not None
    tinted, = drawing.filled("4784AD")
    assert tinted.find("p:spPr/a:solidFill/a:srgbClr/a:alpha", NS).get("val") == "36000"
    line = tinted.find("p:spPr/a:ln", NS)
    assert line.find("a:solidFill/a:srgbClr/a:alpha", NS).get("val") == "65000"
    assert line.find("a:custDash/a:ds", NS).attrib == {"d": "370000", "sp": "160000"}
    assert drawing.svg.findall(".//s:pattern", NS)
    pattern, = drawing.find(".//p:spPr/a:pattFill")
    assert pattern.get("prst") == "upDiag"
    assert pattern.find("a:fgClr/a:srgbClr", NS).get("val") == "80572F"
    assert pattern.find("a:bgClr/a:srgbClr", NS).get("val") == "F4E8D3"


def test_bar_styles(office_output):
    run_demo("bar_styles", make_figure, check, office_output)


if __name__ == "__main__":
    demo_cli("bar_styles", make_figure, check)

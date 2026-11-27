"""Matplotlib scatter, fitted line and vector residual points."""

from demo_support import NS, demo_cli, run_demo


def make_figure():
    """Compare a calibration fit with its residuals."""
    import numpy as np
    from matplotlib import pyplot as plt

    rng = np.random.default_rng(281)
    x = np.linspace(0.4, 9.6, 36)
    y = 1.7 * x + 0.8 + rng.normal(0, 0.95, x.size)
    fitted = np.polyval(np.polyfit(x, y, 1), x)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.2, 3.6), layout="constrained", dpi=300)

    ax1.scatter(x, y, s=22, color="#277C81", edgecolors="none", label="Observation")
    ax1.plot(x, fitted, color="#AE5546", lw=1.6, label="Linear fit")
    ax1.set_xlabel("Reference (V)", fontfamily="Arial", fontsize=11)
    ax1.set_ylabel("Response (mV)", fontfamily="Arial", fontsize=11)
    ax1.set_title("Sensor calibration", fontfamily="Arial Narrow", fontsize=14, fontweight="bold")
    ax1.legend(frameon=False, loc="upper left", fontsize=9)
    ax1.grid(axis="y", color="#D7DEE0", lw=0.7)
    ax1.set_axisbelow(True)

    ax2.scatter(x, y - fitted, s=18, color="#526B91")
    ax2.axhline(0, color="#56666B", lw=0.9, ls="--")
    ax2.set_xlabel("Reference (V)", fontfamily="Arial", fontsize=11)
    ax2.set_ylabel("Residual (mV)", fontfamily="Arial", fontsize=11)
    ax2.set_ylim(-2.8, 2.8)
    ax2.set_title("Fit residuals", fontfamily="Arial Narrow", fontsize=14, fontweight="bold")
    ax2.grid(False)
    return fig


def check(drawing):
    for label, face, size, bold in [
        ("Sensor calibration", "Arial Narrow", "1400", "1"),
        ("Fit residuals", "Arial Narrow", "1400", "1"),
        ("Response (mV)", "Arial", "1100", "0"),
    ]:
        run = drawing.text(label).find(".//a:rPr", NS)
        assert (run.get("sz"), run.get("b"), run.find("a:latin", NS).get("typeface")) == (size, bold, face)
    for label in ("Observation", "Linear fit", "Residual (mV)"):
        drawing.text(label)
    assert len(drawing.filled("277C81")) == 37  # 36 observations and one legend key
    assert drawing.stroked("AE5546") and drawing.stroked("D7DEE0")
    # Each panel has four spines. Only the calibration panel has grid lines.
    width = int(drawing.group.find("p:grpSpPr/a:xfrm/a:ext", NS).get("cx"))
    spine_positions = []
    for shape in drawing.stroked("000000"):
        xf = shape.find("p:spPr/a:xfrm", NS)
        ext = xf.find("a:ext", NS)
        if max(int(ext.get("cx")), int(ext.get("cy"))) > width / 5:
            spine_positions.append(int(xf.find("a:off", NS).get("x")))
    assert sum(x < width / 2 for x in spine_positions) == 4
    assert sum(x > width / 2 for x in spine_positions) == 4
    assert all(int(sh.find("p:spPr/a:xfrm/a:off", NS).get("x")) < width / 2
               for sh in drawing.stroked("D7DEE0"))
    assert len(drawing.filled("526B91")) == 36
    assert not drawing.find(".//p:pic")


def test_calibration(office_output):
    run_demo("calibration", make_figure, check, office_output)


if __name__ == "__main__":
    demo_cli("calibration", make_figure, check)

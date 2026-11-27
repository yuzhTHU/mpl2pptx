"""Chinese characters, a second logarithmic Y axis, and native Office Math."""
from unicodedata import normalize
from demo_support import NS, demo_cli, run_demo


def make_figure():
    """Follow temperature and signal amplitude through one cooling cycle."""
    import numpy as np
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 1, figsize=(11, 6.1), dpi=300)
    ax2 = ax.twinx()

    t = np.linspace(0, 12, 81)
    temperature = 24 + 44 * np.exp(-t / 4.8)
    amplitude = 95 * np.exp(-t / 2.8)

    temp, = ax.plot(t, temperature, lw=2, color="#c44569", label="温度")
    amp, = ax2.plot(t, amplitude, lw=1.8, color="#546de5", ls="--", label="振幅")
    
    ax.set_ylim(20, 72)
    ax.set_ylabel("温度 (°C)", fontfamily="Microsoft YaHei", fontsize=11)
    ax.tick_params(axis="y", colors="#c44569")

    ax2.set_yscale("log")
    ax2.set_ylim(0.7, 150)
    ax2.set_ylabel("振幅 (mV)", fontfamily="Microsoft YaHei", fontsize=11)
    ax2.tick_params(axis="y", colors="#546de5")
    
    ax.set_xlim(0, 12)
    ax.set_xlabel("冷却时间（分钟）", fontfamily="Microsoft YaHei", fontsize=11)
    ax.set_title(r"冷却响应 $A(t)=A_0 e^{-t/\tau}$", fontfamily="Microsoft YaHei", fontsize=14, fontweight="bold")
    ax.grid(axis="y", color="#D7DEE0", linewidth=0.6)
    ax.legend(handles=[temp, amp], loc="upper right", frameon=False,
              prop={"family": "Microsoft YaHei", "size": 11})
    ax.text(0.48, 0.55, r"$A(t)=A_0 e^{-t/\tau}$", transform=ax.transAxes, fontsize=14)

    return fig

def check(drawing):
    title = drawing.text("冷却响应 ")
    for box, size, bold in [
        (title, "1400", "1"),
        (drawing.text("冷却时间（分钟）"), "1100", "0"),
    ]:
        style = box.find("p:txBody/a:p/a:r/a:rPr", NS)
        assert (style.get("sz"), style.get("b")) == (size, bold)
        assert style.find("a:ea", NS).get("typeface") == "Microsoft YaHei"
    inline, = title.xpath("p:txBody/a:p/a14:m/m:oMath", namespaces=NS)
    assert inline.find(".//m:sSup", NS) is not None and inline.find(".//m:sSub", NS) is not None
    assert "τ" in normalize("NFKC", "".join(inline.xpath(".//m:t/text()", namespaces=NS)))
    for name in ("温度 (°C)", "振幅 (mV)", "温度", "振幅"):
        drawing.text(name)
    formulas = drawing.find(".//m:oMath")
    assert any(
        eq.find(".//m:sSub", NS) is not None and 
        eq.find(".//m:sSup", NS) is not None
        for eq in formulas
    )
    assert sum(eq.find(".//m:sSup", NS) is not None for eq in formulas) >= 4
    assert all("\\" not in "".join(eq.itertext()) for eq in formulas)
    assert drawing.stroked("c44569") and drawing.stroked("546de5")


def test_dual_axis(office_output):
    run_demo("dual_axis", make_figure, check, office_output)


if __name__ == "__main__":
    demo_cli("dual_axis", make_figure, check)

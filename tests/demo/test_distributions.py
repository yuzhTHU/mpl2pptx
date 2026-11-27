"""Seaborn box and violin plots, exported with ordinary outlined SVG text."""

from demo_support import NS, demo_cli, run_demo


def make_figure():
    """Compare request latency for three simulated processing modes."""
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns

    rng = np.random.default_rng(193)
    modes = ["Baseline", "Tuned", "Cached"]
    latencies = [rng.lognormal(np.log(median), 0.19, 80) for median in (54, 42, 30)]
    data = {"Mode": np.repeat(modes, 80), "Latency": np.concatenate(latencies)}
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.1, 3.7), sharey=True, layout="constrained", dpi=300)
    sns.boxplot(
        data=data, x="Mode", y="Latency", ax=ax1,
        color="#546de5", saturation=1, width=0.5,
        linewidth=1.1, fliersize=3
    )
    sns.violinplot(
        data=data, x="Mode", y="Latency", ax=ax2,
        color="#c44569", saturation=1,
        linewidth=1.0, inner="quart", cut=0, gridsize=48
    )

    ax1.set_ylabel("Request latency (ms)")
    ax1.set_title("Latency quartiles", fontweight="bold", fontsize=14)
    ax2.set_title("Latency density", fontweight="bold", fontsize=14)
    
    for ax in [ax1, ax2]:
        ax.set_xlabel("Processing mode")
        ax.grid(False)
        sns.despine(ax=ax)
    
    return fig


def check(drawing):
    for label in ("Latency quartiles", "Latency density", "Request latency (ms)"):
        drawing.text(label)
    boxes = drawing.filled("546de5")
    assert len(boxes) == 3
    violins = drawing.filled("c44569")
    assert len(violins) == 3
    assert all(len(v.findall(".//a:lnTo", NS)) >= 50 for v in violins)
    assert not drawing.find(".//p:pic")
    assert not drawing.svg.findall(".//s:text", NS)  # labels were restored from Matplotlib comments


def test_distributions(office_output):
    run_demo("distributions", make_figure, check, office_output, fonttype="path")


if __name__ == "__main__":
    demo_cli("distributions", make_figure, check, fonttype="path")

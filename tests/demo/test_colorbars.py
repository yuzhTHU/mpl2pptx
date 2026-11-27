"""A raster intensity field and a vector classification grid with two colorbar positions."""

from demo_support import NS, demo_cli, run_demo


COLORS = ["#304B75", "#3D9387", "#E5BA65", "#B7514C"]


def make_figure():
    """Show continuous intensity and four discrete zones with independent scales."""
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 4.0), layout="constrained", dpi=300)

    y, x = np.mgrid[-2:2:60j, -2:2:80j]
    intensity = np.exp(-((x+0.5)**2 + 1.6*(y-0.4)**2)) + 0.65*np.exp(-2*((x-0.8)**2 + (y+0.6)**2))
    image = ax1.imshow(
        intensity,
        origin="lower",
        extent=(-2, 2, -2, 2),
        cmap="cividis",
        interpolation="nearest",
        vmin=0,
        vmax=1.05,
        aspect="auto",
        rasterized=True
    )
    fig.colorbar(
        image,
        ax=ax1,
        location="right",
        label="Intensity",
        ticks=[0, 0.5, 1]
    )
    ax1.set_title("Signal field", fontweight="bold", fontsize=14)
    ax1.set_xlabel("Horizontal position", fontsize=11)
    ax1.set_ylabel("Vertical position", fontsize=11)

    row, col = np.indices((6, 8))
    groups = (row + col * 2) % 4
    cmap = mcolors.ListedColormap(COLORS)
    tiles = ax2.pcolormesh(
        groups,
        cmap=cmap,
        norm=mcolors.BoundaryNorm(np.arange(5) - 0.5, 4),
        shading="flat",
        rasterized=False
    )
    fig.colorbar(
        tiles,
        ax=ax2,
        location="top",
        label="Zone class",
        ticks=[0, 1, 2, 3],
        fraction=0.09,
        pad=0.06,
        aspect=28
    )
    ax2.set_xlabel("Grid column", fontsize=11)
    ax2.set_ylabel("Grid row", fontsize=11)
    ax2.set_title("Classification grid", fontweight="bold", fontsize=14)
    ax2.set_xticks([0, 2, 4, 6, 8])
    ax2.set_yticks([0, 2, 4, 6])
    return fig


def check(drawing):
    drawing.text("Signal field")
    assert drawing.find(".//p:pic")
    shapes = [sh for color in COLORS for sh in drawing.filled(color[1:].upper())]
    assert len(shapes) == 48 + 4  # 48 vector cells and four top colorbar swatches
    def position(shape):
        off = shape.find("p:spPr/a:xfrm/a:off", NS)
        return int(off.get("x")), int(off.get("y"))
    top = position(drawing.text("Zone class"))[1]
    assert all(position(sh)[1] > top for sh in shapes)
    right = position(drawing.text("Intensity"))[0]
    images = drawing.find(".//p:pic")
    field = max(images, key=lambda sh: int(sh.find("p:spPr/a:xfrm/a:ext", NS).get("cx")))
    assert right > position(field)[0] + int(field.find("p:spPr/a:xfrm/a:ext", NS).get("cx"))


def test_colorbars(conversion_output):
    run_demo("colorbars", make_figure, check, conversion_output)


if __name__ == "__main__":
    demo_cli("colorbars", make_figure, check)

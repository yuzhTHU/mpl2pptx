"""Public Figure and SVG conversion interfaces, file/stream handling and the conversion sequence."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

from lxml import etree as ET

from .pptx.writer import EMU_PER_PT
from .report import ConversionStats

if TYPE_CHECKING:
    from matplotlib.figure import Figure


POWERPOINT_VERSION = "2024"


def svg2pptx(
    source: str | os.PathLike | bytes | BinaryIO,
    save: str | os.PathLike | BinaryIO | None = None,
    *,
    version: str = POWERPOINT_VERSION,
    backend: str | None = None,
    return_details: bool = False,
) -> Path | bytes | BinaryIO | dict[str, Any]:
    """Convert one SVG to editable PowerPoint objects using the target Office profile.

    Return the output Path, the supplied (rewound) binary stream, or PPTX bytes
    for in-memory input with no destination. File input defaults to <stem>.pptx.
    Set backend to "powerpoint" or "portable" to require that converter.
    None and "auto" prefer installed desktop PowerPoint, then portable.
    An installed backend's conversion error is reported without retrying.
    With return_details=True, return a dict with the result under "output", the
    actual "backend", feature counts and the number of Office shapes and pictures.
    """
    if version != POWERPOINT_VERSION:
        raise ValueError(f"不支持的目标 PowerPoint 版本 {version!r}。当前支持 {POWERPOINT_VERSION}。")
    if isinstance(source, (str, os.PathLike)):
        source = Path(source)
        if save is None:
            save = source.with_name(source.stem + ".pptx")
    output_path = Path(save) if isinstance(save, (str, os.PathLike)) else None
    stats = ConversionStats()
    if output_path is not None:
        if output_path.suffix.lower() != ".pptx":
            raise ValueError("输出文件需使用 .pptx 扩展名。")
        if isinstance(source, Path) and source.resolve() == output_path.resolve():
            raise ValueError("输入和输出需使用不同的文件。")
        _write_pptx(source, output_path, stats, backend)
        output = output_path
    else:
        if save is not None and (save is source or not save.seekable() or not save.writable()):
            raise ValueError("输出需要独立、可写且支持 seek 的二进制流。")
        with tempfile.TemporaryDirectory() as working:
            target = Path(working) / "result.pptx"
            _write_pptx(source, target, stats, backend)
            output = target.read_bytes()
        if save is not None:
            save.seek(0)
            save.write(output)
            save.truncate()
            save.seek(0)
            output = save
    return stats.details(output, version) if return_details else output


def save_pptx(
    fig: Figure,
    save: str | os.PathLike | BinaryIO | None = None,
    *,
    version: str = POWERPOINT_VERSION,
    backend: str | None = None,
    return_details: bool = False,
) -> Path | bytes | BinaryIO | dict[str, Any]:
    """Save a Figure through an in-memory SVG using the same backend selection as svg2pptx."""
    from matplotlib import rc_context

    with BytesIO() as svg:
        # A buffer has no filename beside which Matplotlib could save raster layers.
        with rc_context({"svg.image_inline": True}):
            fig.savefig(svg, format="svg")
        svg.seek(0)
        return svg2pptx(svg, save=save, version=version, backend=backend, return_details=return_details)


def _write_pptx(source, destination, stats, backend):
    """Read one SVG and write its editable shapes into a new presentation."""
    from .pptx import BackendError, get_backend
    from .pptx.restore import restore_editable_shapes
    from .svg.document import figure_viewport, read_svg
    from .svg.prepare import prepare_svg

    converter = get_backend(backend)
    svg = read_svg(source)
    canvas = figure_viewport(svg)
    w, h, _ = canvas
    if not all(72 <= length <= 56 * 72 for length in (w, h)):
        raise ValueError(f"SVG 画幅为 {w:g} × {h:g} 磅。PowerPoint 的页面宽、高各须在 72 至 4032 磅之间。")
    page_size = (round(w * EMU_PER_PT), round(h * EMU_PER_PT))
    with tempfile.TemporaryDirectory() as working:
        stage = Path(working) / "inserted.pptx"
        try:
            _, _, slots = prepare_svg(svg, canvas, detected=stats.detected, mathml_to_omml=converter.mathml_to_omml)
            converter.stage_svg(ET.tostring(svg, encoding="utf-8", xml_declaration=True), stage, w, h)
            restore_editable_shapes(stage, destination, page_size, slots, stats)
        except Exception as exc:
            installed = "PowerPoint" if converter.NAME == "powerpoint" else "svgslide 和 mathml2omml"
            reason = str(exc).strip() or type(exc).__name__
            raise BackendError(f"{installed} 已安装，但 {converter.NAME} 后端转换失败：{reason}") from exc
        stats.backend = converter.NAME

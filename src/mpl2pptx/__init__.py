"""Editable PowerPoint drawings from Matplotlib SVG files."""

__version__ = "0.4.0"

from .api import save_pptx, svg2pptx

__all__ = ["svg2pptx", "save_pptx"]

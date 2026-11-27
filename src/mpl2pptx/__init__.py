"""Editable PowerPoint drawings from Matplotlib SVG files."""

__version__ = "0.3.1"

from .api import save_pptx, svg2pptx

__all__ = ["svg2pptx", "save_pptx"]

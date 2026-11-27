"""Select the installed converter for both SVG geometry and Office Math."""

import sys
from importlib.util import find_spec


BACKEND_CHOICES = ("auto", "powerpoint", "portable")
PORTABLE_INSTALL = 'python -m pip install "mpl2pptx[portable]"'


class BackendError(RuntimeError):
    """The selected backend is installed but could not complete the conversion."""


def missing_portable_dependencies():
    return [name for name in ("svgslide", "mathml2omml") if find_spec(name) is None]


def get_backend(name=None):
    """Resolve a backend once. Only an absent installation permits automatic fallback."""
    if name is not None and name not in BACKEND_CHOICES:
        raise ValueError(f"未知的 backend {name!r}。可选值为 {', '.join(BACKEND_CHOICES)}。")

    office_missing = "未安装 PowerPoint 2024 的 Windows 桌面版。"
    if name != "portable":
        if sys.platform == "win32":
            from . import powerpoint
            try:
                installed = powerpoint.is_installed()
            except OSError as exc:
                raise OSError(f"无法检查 PowerPoint 的安装状态：{exc}") from exc
            if installed:
                return powerpoint
        if name == "powerpoint":
            raise FileNotFoundError(office_missing)

    missing = missing_portable_dependencies()
    if missing:
        prefix = "" if name == "portable" else office_missing
        raise FileNotFoundError(f"{prefix}portable 后端缺少 Python 包 {' 和 '.join(missing)}。"
                                f"请运行 {PORTABLE_INSTALL}")
    from . import portable
    return portable

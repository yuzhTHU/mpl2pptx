"""Stage an SVG as native shapes using desktop PowerPoint on Windows."""

import os
import subprocess
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from lxml import etree as ET

NAME = "powerpoint"


def is_installed():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CLSID"):
            return True
    except FileNotFoundError:
        pass

    # A broken COM registration is a desktop backend failure if PowerPoint exists.
    app_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\POWERPNT.EXE"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            executable = winreg.QueryValue(hive, app_path)
        except FileNotFoundError:
            continue
        if Path(os.path.expandvars(executable.strip('"'))).is_file():
            return True
    return _office_file("POWERPNT.EXE") is not None


def _office_file(filename):
    for env in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if not base:
            continue
        office = Path(base) / "Microsoft Office"
        for folder in (office / "root", office):
            for path in sorted(folder.glob(f"Office*/{filename}"), reverse=True):
                if path.is_file():
                    return path
    return None


@lru_cache(maxsize=1)
def office_math_transform():
    xsl = _office_file("MML2OMML.XSL")
    if xsl is None:
        raise FileNotFoundError("找不到桌面版 Office 的公式转换文件 MML2OMML.XSL。")
    return ET.XSLT(ET.parse(str(xsl)))


def mathml_to_omml(mathml):
    return office_math_transform()(mathml).getroot()


def stage_svg(svg, stage, w, h):
    """Convert the SVG to shapes in PowerPoint and ungroup them on the slide."""
    graphics = stage.with_suffix(".svg")
    graphics.write_bytes(svg)
    env = dict(os.environ, MPL_FIGURE_SVG=str(graphics.resolve()), MPL_FIGURE_STAGE=str(stage),
               MPL_SLIDE_W=str(w), MPL_SLIDE_H=str(h))
    script = files(__package__).joinpath("stage_svg.ps1").read_text(encoding="utf-8")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            env=env, capture_output=True, encoding="utf-8", errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        reason = result.stderr.strip() or result.stdout.strip() or f"PowerShell 退出码 {result.returncode}"
        raise RuntimeError(reason)

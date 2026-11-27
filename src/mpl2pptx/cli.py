"""将 SVG 转换为可编辑的 PowerPoint 文稿。

新文稿页面与 SVG 画幅等大，输出名默认为原文件名加 .pptx。
"""

import argparse
import subprocess
from pathlib import Path
from zipfile import BadZipFile

from lxml import etree as ET

from . import __version__
from .api import POWERPOINT_VERSION, svg2pptx
from .report import ELEMENT_NAMES


def print_details(details):
    print(f"已生成 {details['output']}")
    print(f"目标 PowerPoint {details['version']}，已转换 {details['figures']} 幅 SVG")
    for kind, name in ELEMENT_NAMES.items():
        counts = details["elements"][kind]
        print(f"  {name}  识别 {counts['detected']}，已转换 {counts['converted']}")
    print(f"特殊元素合计  识别 {details['detected']}，已转换 {details['converted']}，"
          f"未转换 {details['unconverted']}")
    print(f"转换结果包含 {details['shapes']} 个原生形状和 {details['pictures']} 个图片对象。")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mpl2pptx", description=__doc__, allow_abbrev=False)
    parser.add_argument("source", type=Path, metavar="INPUT", help="要转换的 SVG 文件路径（必填）")
    parser.add_argument("-o", "--output", type=Path, help="输出 PPTX 路径，默认为原文件名加 .pptx")
    parser.add_argument("--powerpoint-version", choices=[POWERPOINT_VERSION], default=POWERPOINT_VERSION,
                        help="目标 PowerPoint 版本（默认 %(default)s）")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}", help="显示软件包版本")
    args = parser.parse_args(argv)
    if args.source.suffix.lower() != ".svg":
        parser.error("输入文件需使用 .svg 扩展名。")
    try:
        details = svg2pptx(args.source, save=args.output, version=args.powerpoint_version, return_details=True)
    except (OSError, ValueError, BadZipFile, ET.XMLSyntaxError, subprocess.CalledProcessError) as e:
        parser.exit(1, f"{e}\n")
    print_details(details)

"""CLI options, required input paths and printed statistics."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mpl2pptx import __version__, cli
from mpl2pptx.report import ConversionStats


def test_module_cli_works_from_another_directory(tmp_path):
    source_dir = Path(__file__).resolve().parents[1] / "src"
    result = subprocess.run([sys.executable, "-m", "mpl2pptx", "--version"], cwd=tmp_path,
                            env={**os.environ, "PYTHONPATH": str(source_dir)},
                            text=True, capture_output=True, check=True)
    assert result.stdout.strip() == f"mpl2pptx {__version__}"


@pytest.mark.parametrize(("output_args", "expected_save"), [
    ([], None), (["-o", "choice.pptx"], Path("choice.pptx")),
    (["--output", "choice.pptx"], Path("choice.pptx")),
])
def test_cli_routes_svg_and_prints_report(monkeypatch, capsys, output_args, expected_save):
    output_path = expected_save or Path("demo.pptx")

    def spy(source, *, save, version, return_details):
        assert (source, save, version, return_details) == (Path("demo.svg"), expected_save, "2024", True)
        stats = ConversionStats()
        stats.detected["hatches"], stats.converted["hatches"] = 2, 1
        stats.figures, stats.shapes, stats.pictures = 1, 4, 1
        return stats.details(output_path, version)

    monkeypatch.setattr(cli, "svg2pptx", spy)
    cli.main(["demo.svg", *output_args, "--powerpoint-version", "2024"])
    output = capsys.readouterr().out
    assert str(output_path) in output and "图案填充  识别 2，已转换 1" in output
    assert "未转换 1" in output and "4 个原生形状和 1 个图片对象" in output


@pytest.mark.parametrize("args", [
    ["test.svg", "output.pptx"],
    ["input.pptx"],
    ["input.svg", "--svg", "figure.svg"],
    ["test.svg", "--powerpoint-version", "2019"],
    ["test.svg", "-v", "2024"],
])
def test_cli_rejects_invalid_arguments(args):
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


def test_cli_package_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0 and capsys.readouterr().out.strip() == f"mpl2pptx {__version__}"


@pytest.mark.parametrize(("files", "args"), [
    ([], []),
    (["test.svg"], []),
    (["only.svg"], []),
    (["test.svg", "other.svg"], []),
    (["first.svg", "second.svg"], []),
    (["test.svg"], ["-o", "test.pptx"]),
])
def test_missing_input_exits_before_conversion(tmp_path, monkeypatch, capsys, files, args):
    monkeypatch.chdir(tmp_path)
    for name in files:
        (tmp_path / name).touch()
    existing = tmp_path / "test.pptx"
    existing.write_bytes(b"prior result")

    def unexpected_conversion(*args, **kwargs):
        pytest.fail("Conversion was called without an explicit input")

    monkeypatch.setattr(cli, "svg2pptx", unexpected_conversion)
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2 and "INPUT" in capsys.readouterr().err
    assert list(tmp_path.glob("*.pptx")) == [existing]
    assert existing.read_bytes() == b"prior result"

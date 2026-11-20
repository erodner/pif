"""Command line interface: `pif scan <files or directories>`."""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from enum import Enum
from pathlib import Path

import typer

from .detect.patterns import PatternDetector
from .model import Report, Severity
from .report import json_report, sarif_report, text_report
from .scanner import ScanOptions, scan

app = typer.Typer(add_completion=False, help="Find hidden and visible prompt-injection patterns in PDF documents.")


class Fmt(str, Enum):
    text = "text"
    json = "json"
    sarif = "sarif"


class FailOn(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    never = "never"


def _collect(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*") if q.suffix.lower() == ".pdf" and q.is_file()))
        else:
            files.append(p)
    return files


def _scan_one(args: tuple[str, ScanOptions]) -> Report:
    path, opt = args
    return scan(path, opt)


@app.callback()
def main() -> None:
    """promptinjectorfinder."""


@app.command("scan")
def scan_cmd(
    paths: list[Path] = typer.Argument(..., exists=True, help="PDF files or directories (searched recursively)."),
    fmt: Fmt = typer.Option(Fmt.text, "--format", "-f", help="Output format."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write report to file instead of stdout."),
    fail_on: FailOn = typer.Option(FailOn.high, help="Exit with code 1 if a finding of at least this severity exists."),
    min_severity: Severity = typer.Option(Severity.LOW, help="Minimum severity shown in text output."),
    no_render: bool = typer.Option(False, "--no-render", help="Skip pixel-based visibility check (faster, misses colour/cover tricks)."),
    rules: Path | None = typer.Option(None, help="JSON file with extra pattern rules [{id,label,pattern,score}]."),
    jobs: int = typer.Option(1, "--jobs", "-j", min=1, help="Parallel worker processes."),
) -> None:
    """Scan PDFs and report suspected prompt injections."""
    files = _collect(paths)
    if not files:
        typer.echo("no PDF files found", err=True)
        raise typer.Exit(2)

    opt = ScanOptions(render=not no_render)
    if rules:
        opt.detectors = [PatternDetector.with_extra_rules(rules)]

    if jobs > 1 and len(files) > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            reports = list(ex.map(_scan_one, [(str(f), opt) for f in files]))
    else:
        reports = [scan(str(f), opt) for f in files]

    if fmt is Fmt.json:
        out = json_report.render(reports)
    elif fmt is Fmt.sarif:
        out = sarif_report.render(reports)
    else:
        out = text_report.render(reports, min_severity)

    if output:
        output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out + ("\n" if not out.endswith("\n") else ""))

    if any(r.errors for r in reports) and not any(r.findings for r in reports):
        raise typer.Exit(2)
    if fail_on is not FailOn.never:
        threshold = Severity(fail_on.value).rank
        if any(f.severity.rank >= threshold for r in reports for f in r.findings):
            raise typer.Exit(1)


if __name__ == "__main__":
    app()

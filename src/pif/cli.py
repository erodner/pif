"""Command line interface: `pif scan <files or directories>` and `pif models ...`."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from .detect.patterns import PatternDetector
from .model import Report, Severity
from .report import html_report, json_report, sarif_report, text_report
from .scanner import ScanOptions, scan

app = typer.Typer(add_completion=False, help="Find hidden and visible prompt-injection patterns in PDF documents.")
models_app = typer.Typer(help="Manage local ML models (optional, needs the [ml] extra).")
app.add_typer(models_app, name="models")

err = Console(stderr=True)


class Fmt(str, Enum):
    text = "text"
    json = "json"
    sarif = "sarif"
    html = "html"


class FailOn(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    never = "never"


class MlMode(str, Enum):
    auto = "auto"  # use installed models
    on = "on"  # require models
    off = "off"


# ------------------------------------------------------------------------------ file discovery


def collect_pdfs(paths: list[Path], recursive: bool = True, include_hidden: bool = False) -> list[Path]:
    """Expand files and directories into a sorted, de-duplicated list of PDF files.

    Directories are walked recursively (unless `recursive` is False); files are matched by a
    case-insensitive `.pdf` extension. Hidden files/directories are skipped unless asked for.
    Files given explicitly are always included, whatever their extension.
    """
    seen: set[Path] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            out.append(p)

    for p in paths:
        if p.is_file():
            add(p)
            continue
        if not p.is_dir():
            continue
        for root, dirs, files in os.walk(p, onerror=lambda e: err.print(f"[yellow]skip {e.filename}: {e.strerror}")):
            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            dirs.sort()
            for name in sorted(files):
                if name.lower().endswith(".pdf") and (include_hidden or not name.startswith(".")):
                    add(Path(root) / name)
            if not recursive:
                break
    return out


# ------------------------------------------------------------------------------ workers

_WORKER_ML = None


_WORKER_OCR = None


def _worker_init(ml_mode: str, ocr_mode: str, threads: int) -> None:
    global _WORKER_ML, _WORKER_OCR
    # Share the cores between workers instead of every ONNX session grabbing all of them.
    os.environ.setdefault("PIF_THREADS", str(threads))
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    _WORKER_ML = _load_ml(MlMode(ml_mode), quiet=True)
    _WORKER_OCR = _load_ocr(MlMode(ocr_mode), quiet=True)


def _scan_in_worker(path: str, opt: ScanOptions) -> Report:
    opt.ml = _WORKER_ML
    opt.glyph_checker = _WORKER_OCR
    return scan(path, opt)


def _load_ocr(mode: MlMode, quiet: bool = False):
    if mode is MlMode.off:
        return None
    from .visibility.ocr import GlyphChecker

    checker = GlyphChecker.load()
    if checker is None and mode is MlMode.on:
        err.print("[red]error:[/] OCR needs `pip install promptinjectorfinder[ocr]`")
        raise typer.Exit(2)
    if not quiet:
        err.print(f"[dim]OCR glyph check: {'on' if checker else 'not installed'}[/]")
    return checker


def _load_ml(mode: MlMode, quiet: bool = False):
    if mode is MlMode.off:
        return None
    from .ml.cascade import MLCascade

    try:
        ml = MLCascade.load(require=mode is MlMode.on)
    except RuntimeError as e:
        err.print(f"[red]error:[/] {e}")
        raise typer.Exit(2)
    if not quiet:
        if ml is None:
            err.print("[dim]ML detectors: not installed (rules only; see `pif models download`)[/]")
        else:
            err.print(f"[dim]ML detectors: {ml.description}[/]")
    return ml


# ------------------------------------------------------------------------------ commands


@app.command("scan")
def scan_cmd(
    paths: list[Path] = typer.Argument(..., exists=True, help="PDF files or directories (searched recursively)."),
    fmt: Fmt = typer.Option(Fmt.text, "--format", "-f", help="Output format."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write report to file instead of stdout."),
    fail_on: FailOn = typer.Option(FailOn.high, help="Exit with code 1 if a finding of at least this severity exists."),
    min_severity: Severity = typer.Option(Severity.LOW, help="Minimum severity shown in text output."),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r/-R", help="Descend into subdirectories."),
    include_hidden: bool = typer.Option(False, "--include-hidden", help="Also scan hidden files and directories."),
    no_render: bool = typer.Option(False, "--no-render", help="Skip pixel-based visibility check (faster, misses colour/cover tricks)."),
    ml: MlMode = typer.Option(MlMode.auto, "--ml", help="ML detectors: auto = use installed models."),
    ocr: MlMode = typer.Option(MlMode.auto, "--ocr", help="OCR glyph-remapping check: auto = use if installed."),
    rules: Path | None = typer.Option(None, help="JSON file with extra pattern rules [{id,label,pattern,score}]."),
    jobs: int = typer.Option(1, "--jobs", "-j", min=1, help="Parallel worker processes."),
    progress: bool | None = typer.Option(None, "--progress/--no-progress", help="Progress bar (default: on when stderr is a terminal)."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No progress bar or status messages."),
) -> None:
    """Scan PDFs (files or whole directory trees) and report suspected prompt injections."""
    files = collect_pdfs(paths, recursive=recursive, include_hidden=include_hidden)
    if not files:
        err.print("[red]no PDF files found[/]")
        raise typer.Exit(2)

    opt = ScanOptions(render=not no_render)
    if rules:
        opt.detectors = [PatternDetector.with_extra_rules(rules)]

    show_progress = (not quiet) and (progress if progress is not None else err.is_terminal)
    workers = min(jobs, len(files))
    if workers <= 1:
        opt.ml = _load_ml(ml, quiet=quiet)
        opt.glyph_checker = _load_ocr(ocr, quiet=quiet)
    elif not quiet:
        err.print(f"[dim]scanning {len(files)} PDF(s) with {workers} workers[/]")

    reports: dict[int, Report] = {}
    with Progress(
        TextColumn("[bold blue]scanning"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("<"),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[current]}", justify="left"),
        console=err,
        disable=not show_progress,
        transient=False,
    ) as bar:
        task = bar.add_task("scan", total=len(files), current="")

        def done(i: int, r: Report) -> None:
            reports[i] = r
            flag = {"high": "[red]HIGH[/]", "medium": "[yellow]MEDIUM[/]"}.get(r.max_severity.value if r.max_severity else "", "")
            bar.update(task, advance=1, current=f"{_short(files[i])} {flag}")

        if workers <= 1:
            for i, f in enumerate(files):
                bar.update(task, current=_short(f))
                done(i, scan(str(f), opt))
        else:
            with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init, initargs=(ml.value, ocr.value, max(1, (os.cpu_count() or 1) // workers))) as ex:
                futures = {ex.submit(_scan_in_worker, str(f), opt): i for i, f in enumerate(files)}
                for fut in as_completed(futures):
                    i = futures[fut]
                    try:
                        done(i, fut.result())
                    except Exception as e:  # noqa: BLE001 - worker crash (e.g. MuPDF abort)
                        done(i, Report(path=str(files[i]), errors=[f"worker failed: {e}"]))

    ordered = [reports[i] for i in range(len(files))]
    if fmt is Fmt.json:
        out = json_report.render(ordered)
    elif fmt is Fmt.sarif:
        out = sarif_report.render(ordered)
    elif fmt is Fmt.html:
        out = html_report.render(ordered)
    else:
        out = text_report.render(ordered, min_severity)

    if output:
        output.write_text(out, encoding="utf-8")
        if not quiet:
            err.print(f"[dim]report written to {output}[/]")
    else:
        sys.stdout.write(out + ("\n" if not out.endswith("\n") else ""))

    if not quiet:
        _summary(ordered)

    if any(r.errors for r in ordered) and not any(r.findings for r in ordered):
        raise typer.Exit(2)
    if fail_on is not FailOn.never:
        threshold = Severity(fail_on.value).rank
        if any(f.severity.rank >= threshold for r in ordered for f in r.findings):
            raise typer.Exit(1)


def _short(p: Path, width: int = 40) -> str:
    s = str(p)
    return s if len(s) <= width else "…" + s[-(width - 1) :]


def _summary(reports: list[Report]) -> None:
    by = {s: sum(1 for r in reports if r.max_severity is s) for s in Severity}
    errors = sum(1 for r in reports if r.errors)
    clean = sum(1 for r in reports if r.max_severity is None and not r.errors)
    err.print(
        f"[bold]{len(reports)} PDF(s):[/] [red]{by[Severity.HIGH]} high[/], [yellow]{by[Severity.MEDIUM]} medium[/], "
        f"{by[Severity.LOW]} low, [green]{clean} clean[/]" + (f", [red]{errors} error(s)[/]" if errors else "")
    )


@models_app.command("list")
def models_list() -> None:
    """Show available models and whether they are installed."""
    from .ml import store

    err.print(f"cache: {store.cache_dir()}")
    for spec in store.MODELS.values():
        where = store.find_model(spec.name)
        state = f"[green]installed[/] {where}" if where else "[dim]not installed[/]"
        typer.echo(f"{spec.name:<15} {spec.kind:<10} {spec.license:<11} {spec.repo}")
        err.print(f"                {spec.description}\n                {state}")


@models_app.command("download")
def models_download(
    names: list[str] = typer.Argument(None, help="Models to download (default: all)."),
) -> None:
    """Download (and verify) models from the Hugging Face Hub into the local cache."""
    from .ml import store

    for name in names or list(store.MODELS):
        if name not in store.MODELS:
            err.print(f"[red]unknown model {name}[/]")
            raise typer.Exit(2)
        with Progress(TextColumn(f"{name} {{task.fields[file]}}"), BarColumn(), MofNCompleteColumn(), console=err) as bar:
            task = bar.add_task(name, total=None, file="")

            def cb(file: str, done: int, total: int) -> None:
                bar.update(task, completed=done // 1_000_000, total=(total // 1_000_000) or None, file=file + " (MB)")

            path = store.download(name, progress=cb)
        err.print(f"[green]✓[/] {name} → {path}")


@models_app.command("remove")
def models_remove(names: list[str] = typer.Argument(..., help="Models to delete from the cache.")) -> None:
    """Delete downloaded models."""
    from .ml import store

    for name in names:
        store.remove(name)
        err.print(f"removed {name}")


if __name__ == "__main__":
    app()

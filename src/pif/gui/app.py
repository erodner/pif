"""PySide6 desktop app: drop PDFs or folders, scan, inspect findings with page previews."""

from __future__ import annotations

import sys
from concurrent.futures import CancelledError, ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf
from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, runner
from ..cli import collect_pdfs
from ..model import Finding, Report, Severity
from ..preview import finding_png
from ..report import html_report, json_report
from ..scanner import ScanOptions

APP_NAME = "Prompt Injection Finder"
ORG = "promptinjectorfinder"

SEVERITY_COLORS = {
    Severity.HIGH: "#d32f2f",
    Severity.MEDIUM: "#ef8a00",
    Severity.LOW: "#3d7bd9",
    Severity.INFO: "#7a828c",
}


# ----------------------------------------------------------------------------- settings


class Settings:
    def __init__(self) -> None:
        self.q = QSettings(ORG, "app")

    def _get(self, key: str, default):
        v = self.q.value(key, default)
        if isinstance(default, bool):
            return v in (True, "true", "1", 1)
        if isinstance(default, int):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default
        return v

    render = property(lambda s: s._get("render", True), lambda s, v: s.q.setValue("render", v))
    embedding = property(lambda s: s._get("embedding", True), lambda s, v: s.q.setValue("embedding", v))
    classifier = property(lambda s: s._get("classifier", True), lambda s, v: s.q.setValue("classifier", v))
    ocr = property(lambda s: s._get("ocr", True), lambda s, v: s.q.setValue("ocr", v))
    workers = property(lambda s: s._get("workers", 2), lambda s, v: s.q.setValue("workers", v))


class ModelDownloader(QObject):
    progress = Signal(str, int, int)
    finished = Signal(str)  # error message or ""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    @Slot()
    def run(self) -> None:
        from ..ml import store

        try:
            store.download(self.name, progress=lambda f, d, t: self.progress.emit(f, d, t))
            self.finished.emit("")
        except Exception as e:  # noqa: BLE001
            self.finished.emit(str(e))


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings
        form = QFormLayout()

        self.render = QCheckBox("Pixel visibility check (white text, covered or clipped text)")
        self.embedding = QCheckBox("Embedding similarity (catches paraphrased injections)")
        self.classifier = QCheckBox("Injection classifier on hidden and non-visual text")
        self.ocr = QCheckBox("OCR check for fonts that display different text than they contain")
        self.workers = QSpinBox()
        self.workers.setRange(1, 16)
        for w, v in [(self.render, settings.render), (self.embedding, settings.embedding),
                     (self.classifier, settings.classifier), (self.ocr, settings.ocr)]:
            w.setChecked(v)
        self.workers.setValue(settings.workers)
        form.addRow(self.render)
        form.addRow(self.embedding)
        form.addRow(self.classifier)
        form.addRow(self.ocr)
        form.addRow("Parallel scans", self.workers)

        self.model_status = QLabel()
        self.model_status.setWordWrap(True)
        self.download_btn = QPushButton("Download classifier (740 MB)")
        self.download_btn.clicked.connect(self._download)
        self.download_bar = QProgressBar()
        self.download_bar.hide()
        form.addRow(self.model_status)
        form.addRow(self.download_btn)
        form.addRow(self.download_bar)
        self._refresh_models()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._thread: QThread | None = None

    def _refresh_models(self) -> None:
        try:
            from ..ml import store
        except ImportError:
            self.model_status.setText("ML support is not included in this build.")
            self.download_btn.setEnabled(False)
            return
        lines = []
        for spec in store.MODELS.values():
            where = store.find_model(spec.name)
            lines.append(f"<b>{spec.name}</b>: {'installed' if where else 'not installed'} — {spec.description}")
        self.model_status.setText("<br>".join(lines))
        self.download_btn.setVisible(store.find_model(store.DEFAULT_CLASSIFIER) is None)

    def _download(self) -> None:
        from ..ml import store

        self.download_btn.setEnabled(False)
        self.download_bar.show()
        self._thread = QThread(self)
        self._dl = ModelDownloader(store.DEFAULT_CLASSIFIER)
        self._dl.moveToThread(self._thread)
        self._thread.started.connect(self._dl.run)
        self._dl.progress.connect(self._on_progress)
        self._dl.finished.connect(self._on_done)
        self._thread.start()

    @Slot(str, int, int)
    def _on_progress(self, file: str, done: int, total: int) -> None:
        if total:
            self.download_bar.setRange(0, 1000)
            self.download_bar.setValue(int(1000 * done / total))
        self.download_bar.setFormat(f"{file}: {done // 1_000_000} / {total // 1_000_000} MB")

    @Slot(str)
    def _on_done(self, error: str) -> None:
        self._thread.quit()
        self._thread.wait()
        self.download_bar.hide()
        self.download_btn.setEnabled(True)
        if error:
            QMessageBox.warning(self, "Download failed", error)
        self._refresh_models()

    def accept(self) -> None:
        s = self.settings
        s.render, s.embedding, s.classifier = self.render.isChecked(), self.embedding.isChecked(), self.classifier.isChecked()
        s.ocr, s.workers = self.ocr.isChecked(), self.workers.value()
        super().accept()


# ----------------------------------------------------------------------------- scanning


class ScanWorker(QObject):
    """Runs scans in a process pool (MuPDF is not thread-safe; crashes stay isolated)."""

    status = Signal(str)
    file_done = Signal(int, object)
    finished = Signal()

    def __init__(self, paths: list[str], settings: Settings):
        super().__init__()
        self.paths = paths
        self.workers = max(1, min(settings.workers, len(paths)))
        self.opt = ScanOptions(render=settings.render)
        self.init = (
            runner.AUTO if (settings.embedding or settings.classifier) else runner.OFF,
            runner.AUTO if settings.ocr else runner.OFF,
            runner.threads_per_worker(self.workers),
            settings.embedding,
            settings.classifier,
        )
        self._executor: ProcessPoolExecutor | None = None
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        self.status.emit("Loading detectors…")
        try:
            self._executor = ProcessPoolExecutor(max_workers=self.workers, initializer=runner.worker_init, initargs=self.init)
            futures = {self._executor.submit(runner.scan_in_worker, p, self.opt): i for i, p in enumerate(self.paths)}
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    report = fut.result()
                except CancelledError:
                    continue
                except Exception as e:  # noqa: BLE001 - worker died (e.g. MuPDF abort)
                    report = Report(path=self.paths[i], errors=[f"scan failed: {e}"])
                self.file_done.emit(i, report)
                if self._cancelled:
                    break
        finally:
            if self._executor:
                self._executor.shutdown(wait=True, cancel_futures=True)
            self.finished.emit()

    def cancel(self) -> None:
        self._cancelled = True
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)


# ----------------------------------------------------------------------------- main window


class DropTable(QTableWidget):
    dropped = Signal(list)

    def __init__(self, *args):
        super().__init__(*args)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        self.dropped.emit(paths)
        e.acceptProposedAction()


class MainWindow(QMainWindow):
    COLS = ["File", "Result", "Findings", "Pages", "Folder"]
    FCOLS = ["Severity", "Page", "Where", "Techniques", "Detail"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.settings = Settings()
        self.paths: list[Path] = []
        self.reports: dict[int, Report] = {}
        self._thread: QThread | None = None
        self._worker: ScanWorker | None = None
        self._build()

    # --- layout ---------------------------------------------------------------------------
    def _build(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(text, slot, shortcut=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            tb.addAction(a)
            return a

        act("Add Files…", self.add_files, QKeySequence.Open)
        act("Add Folder…", self.add_folder, "Ctrl+Shift+O")
        tb.addSeparator()
        self.scan_action = act("Scan", self.start_scan, "Ctrl+R")
        self.stop_action = act("Stop", self.stop_scan)
        self.stop_action.setEnabled(False)
        act("Clear", self.clear)
        tb.addSeparator()
        act("Export HTML…", lambda: self.export("html"))
        act("Export JSON…", lambda: self.export("json"))
        tb.addSeparator()
        act("Settings…", self.open_settings, QKeySequence.Preferences)
        act("About", self.about)

        self.files = DropTable(0, len(self.COLS))
        self.files.setHorizontalHeaderLabels(self.COLS)
        self.files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files.setSortingEnabled(False)
        self.files.verticalHeader().hide()
        hdr = self.files.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Interactive)
        hdr.resizeSection(4, 120)
        self.files.itemSelectionChanged.connect(self.show_file)
        self.files.cellDoubleClicked.connect(self.open_pdf)
        self.files.dropped.connect(self.add_paths)

        self.empty = QLabel("Drop PDF files or folders here\nor use “Add Files…” / “Add Folder…”")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color: palette(mid); font-size: 16px; border: 2px dashed palette(mid); border-radius: 12px;")
        self.empty.setAcceptDrops(False)
        self.file_stack = QStackedWidget()
        self.file_stack.addWidget(self.empty)
        self.file_stack.addWidget(self.files)
        self.setAcceptDrops(True)

        self.findings = QTableWidget(0, len(self.FCOLS))
        self.findings.setHorizontalHeaderLabels(self.FCOLS)
        self.findings.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.findings.setSelectionMode(QAbstractItemView.SingleSelection)
        self.findings.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.findings.verticalHeader().hide()
        fh = self.findings.horizontalHeader()
        for c in range(4):
            fh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        fh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.findings.itemSelectionChanged.connect(self.show_finding)

        self.preview = QLabel("Select a finding to see the page region")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(140)
        scroll = QScrollArea()
        scroll.setWidget(self.preview)
        scroll.setWidgetResizable(True)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Extracted text of the selected finding")

        detail = QSplitter(Qt.Vertical)
        detail.addWidget(scroll)
        detail.addWidget(self.text)
        detail.setSizes([300, 160])

        right = QSplitter(Qt.Vertical)
        right.addWidget(self.findings)
        right.addWidget(detail)
        right.setSizes([260, 480])

        main = QSplitter(Qt.Horizontal)
        main.addWidget(self.file_stack)
        main.addWidget(right)
        main.setSizes([480, 800])
        self.setCentralWidget(main)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.hide()
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)

    # --- drag & drop on the whole window ---------------------------------------------------
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        self.add_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    # --- file list -------------------------------------------------------------------------
    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add PDF files", "", "PDF files (*.pdf *.PDF);;All files (*)")
        self.add_paths([Path(f) for f in files])

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add folder (scanned recursively)")
        if d:
            self.add_paths([Path(d)])

    @Slot(list)
    def add_paths(self, paths: list[Path]) -> None:
        if self._thread is not None:
            return
        known = {p.resolve() for p in self.paths}
        new = [p for p in collect_pdfs(paths) if p.resolve() not in known]
        for p in new:
            self.paths.append(p)
            row = self.files.rowCount()
            self.files.insertRow(row)
            self._set_row(row, p, None)
        self.file_stack.setCurrentIndex(1 if self.paths else 0)
        self.status_label.setText(f"{len(self.paths)} PDF(s) in list" + (f" (+{len(new)} added)" if new else ""))

    def _set_row(self, row: int, path: Path, report: Report | None, status: str = "not scanned") -> None:
        result = status
        color = None
        if report is not None:
            ms = report.max_severity
            if report.errors and not report.findings:
                result, color = "error", SEVERITY_COLORS[Severity.HIGH]
            elif ms is None:
                result, color = "clean", "#2e7d32"
            else:
                result, color = ms.value.upper(), SEVERITY_COLORS[ms]
        values = [
            path.name,
            result,
            "" if report is None else str(len(report.findings)),
            "" if report is None else str(report.pages),
            str(path.parent),
        ]
        for c, v in enumerate(values):
            item = QTableWidgetItem(v)
            item.setToolTip(str(path) if c in (0, 4) else v)
            if c == 1 and color:
                item.setForeground(QColor(color))
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.files.setItem(row, c, item)

    def clear(self) -> None:
        if self._thread is not None:
            return
        self.paths.clear()
        self.reports.clear()
        self.files.setRowCount(0)
        self.findings.setRowCount(0)
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Select a finding to see the page region")
        self.text.clear()
        self.file_stack.setCurrentIndex(0)
        self.status_label.setText("Ready")

    def open_pdf(self, row: int, _col: int) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths[row].resolve())))

    # --- scanning --------------------------------------------------------------------------
    def start_scan(self) -> None:
        if self._thread is not None or not self.paths:
            return
        self.reports.clear()
        for row, p in enumerate(self.paths):
            self._set_row(row, p, None, "queued")
        self.findings.setRowCount(0)
        self.progress.setRange(0, len(self.paths))
        self.progress.setValue(0)
        self.progress.show()
        self.scan_action.setEnabled(False)
        self.stop_action.setEnabled(True)

        self._thread = QThread(self)
        self._worker = ScanWorker([str(p) for p in self.paths], self.settings)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self.status_label.setText)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_scan_finished)
        self._thread.start()

    def stop_scan(self) -> None:
        if self._worker:
            self.status_label.setText("Stopping…")
            self._worker.cancel()

    @Slot(int, object)
    def _on_file_done(self, i: int, report: Report) -> None:
        self.reports[i] = report
        self._set_row(i, self.paths[i], report)
        n = len(self.reports)
        self.progress.setValue(n)
        self.status_label.setText(f"Scanned {n}/{len(self.paths)}: {self.paths[i].name}")
        if self.files.currentRow() == i:
            self.show_file()

    @Slot()
    def _on_scan_finished(self) -> None:
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self.progress.hide()
        self.scan_action.setEnabled(True)
        self.stop_action.setEnabled(False)
        reps = list(self.reports.values())
        high = sum(1 for r in reps if r.max_severity is Severity.HIGH)
        med = sum(1 for r in reps if r.max_severity is Severity.MEDIUM)
        clean = sum(1 for r in reps if r.max_severity is None and not r.errors)
        self.status_label.setText(f"Done: {len(reps)}/{len(self.paths)} scanned — {high} high, {med} medium, {clean} clean")
        for row, p in enumerate(self.paths):
            if row not in self.reports:
                self._set_row(row, p, None, "not scanned")
        if self.files.currentRow() < 0 and self.paths:
            self.files.selectRow(0)

    # --- details ---------------------------------------------------------------------------
    def _current_report(self) -> Report | None:
        row = self.files.currentRow()
        return self.reports.get(row) if row >= 0 else None

    def show_file(self) -> None:
        self.findings.setRowCount(0)
        self.preview.setPixmap(QPixmap())
        self.text.clear()
        report = self._current_report()
        if report is None:
            self.preview.setText("Not scanned yet")
            return
        if report.errors:
            self.text.setPlainText("\n".join(report.errors))
        if not report.findings:
            self.preview.setText("No findings" if not report.errors else "Scan failed")
            return
        self.preview.setText("Select a finding to see the page region")
        for f in report.findings:
            row = self.findings.rowCount()
            self.findings.insertRow(row)
            vals = [f.severity.value.upper(), str(f.page or ""), f.carrier,
                    ", ".join(t.value for t in f.techniques), f.detail]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setToolTip(v)
                if c == 0:
                    item.setForeground(QColor(SEVERITY_COLORS[f.severity]))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.findings.setItem(row, c, item)
        self.findings.selectRow(0)

    def show_finding(self) -> None:
        report = self._current_report()
        row = self.findings.currentRow()
        if report is None or row < 0 or row >= len(report.findings):
            return
        f: Finding = report.findings[row]
        info = [f.detail]
        if f.rules:
            info.append("Rules: " + "; ".join(f.rules))
        info.append("")
        info.append(f.text)
        self.text.setPlainText("\n".join(info))
        png = None
        if f.page and f.bboxes:
            try:
                with pymupdf.open(report.path, filetype="pdf") as doc:
                    dpr = max(1.0, self.devicePixelRatioF())
                    png = finding_png(doc, f, zoom=1.6 * dpr, max_width_px=int(1400 * dpr))
            except Exception:  # noqa: BLE001
                png = None
        if png:
            pm = QPixmap()
            pm.loadFromData(png, "PNG")
            pm.setDevicePixelRatio(max(1.0, self.devicePixelRatioF()))
            self.preview.setPixmap(pm)
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("No page preview (text is not on a page, or lies outside it)")

    # --- export / misc ---------------------------------------------------------------------
    def export(self, kind: str) -> None:
        reps = [self.reports[i] for i in sorted(self.reports)]
        if not reps:
            QMessageBox.information(self, APP_NAME, "Scan some files first.")
            return
        filt = "HTML report (*.html)" if kind == "html" else "JSON (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"prompt-injection-report.{kind}", filt)
        if not path:
            return
        out = html_report.render(reps) if kind == "html" else json_report.render(reps)
        Path(path).write_text(out, encoding="utf-8")
        self.status_label.setText(f"Report written to {path}")
        if kind == "html":
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_settings(self) -> None:
        SettingsDialog(self.settings, self).exec()

    def about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br><br>Finds hidden and visible prompt-injection patterns in PDF "
            "documents, fully offline.<br><br>Free software under the GNU AGPL v3 or later. "
            "Source code: see the project repository.<br>Bundled components: PyMuPDF (AGPL), Qt/PySide6 (LGPL), "
            "ONNX Runtime (MIT), RapidOCR (Apache-2.0), all-MiniLM-L6-v2 (Apache-2.0).",
        )

    def closeEvent(self, e):  # noqa: N802
        if self._worker:
            self._worker.cancel()
        if self._thread:
            self._thread.quit()
            self._thread.wait(5000)
        super().closeEvent(e)


# ----------------------------------------------------------------------------- entry points


class _App(QApplication):
    """Handles macOS "Open With"/Dock drops, which arrive as FileOpen events, not argv."""

    def __init__(self, argv):
        super().__init__(argv)
        self.window: MainWindow | None = None
        self.pending: list[Path] = []

    def event(self, e):
        if e.type() == QEvent.FileOpen:
            path = Path(e.file())
            if self.window is not None:
                self.window.add_paths([path])
            else:
                self.pending.append(path)
            return True
        return super().event(e)


def main(argv: list[str] | None = None) -> int:
    import multiprocessing

    multiprocessing.freeze_support()
    argv = list(sys.argv if argv is None else argv)

    # The frozen app doubles as the CLI:  "Prompt Injection Finder" --cli scan folder/
    if len(argv) > 1 and argv[1] == "--cli":
        from ..cli import app as cli_app

        sys.argv = [argv[0], *argv[2:]]
        try:
            cli_app()
        except SystemExit as e:
            return int(e.code or 0)
        return 0
    if len(argv) > 1 and argv[1] == "--selftest":
        return runner.selftest()

    app = _App(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG)
    win = MainWindow()
    app.window = win
    win.show()
    if app.pending:
        win.add_paths(app.pending)
    if "--smoke-gui" in argv:  # CI check of packaged builds: Qt starts, window opens, app exits
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, app.quit)
        argv = [a for a in argv if a != "--smoke-gui"]
    files = [Path(a) for a in argv[1:] if not a.startswith("-")]
    if files:
        win.add_paths(files)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

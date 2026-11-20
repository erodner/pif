from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

sys.path.insert(0, str(Path(__file__).parent))
from make_fixtures import build_all  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_gui_scan_end_to_end(qapp, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtCore import QSettings

    from pif.gui.app import MainWindow

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    build_all(FIXTURES)

    win = MainWindow()
    win.settings.embedding = False  # keep the test fast and model-independent
    win.settings.classifier = False
    win.settings.ocr = False
    win.settings.workers = 2
    win.show()
    win.add_paths([FIXTURES / "clean.pdf", FIXTURES / "white_text.pdf", FIXTURES / "metadata_injection.pdf"])
    win.add_paths([FIXTURES / "clean.pdf"])  # duplicate ignored
    assert win.files.rowCount() == 3

    win.start_scan()
    deadline = time.time() + 120
    while win._thread is not None and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert win._thread is None, "scan did not finish"

    results = {win.files.item(r, 0).text(): win.files.item(r, 1).text() for r in range(3)}
    assert results == {"clean.pdf": "clean", "white_text.pdf": "HIGH", "metadata_injection.pdf": "MEDIUM"}

    row = [r for r in range(3) if win.files.item(r, 0).text() == "white_text.pdf"][0]
    win.files.selectRow(row)
    qapp.processEvents()
    assert win.findings.rowCount() >= 1
    win.findings.selectRow(0)
    qapp.processEvents()
    assert win.preview.pixmap() is not None and not win.preview.pixmap().isNull()
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in win.text.toPlainText().upper()
    win.close()

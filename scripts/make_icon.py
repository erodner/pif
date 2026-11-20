"""Render the app icon (1024 px PNG) with Qt; PyInstaller converts it to .icns/.ico."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPen  # noqa: E402

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "build/icon.png"
    app = QGuiApplication([])
    S = 1024
    img = QImage(S, S, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    # rounded tile
    p.setBrush(QBrush(QColor("#1f3b63")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(64, 64, 896, 896), 200, 200)
    # page
    p.setBrush(QBrush(QColor("#ffffff")))
    p.drawRoundedRect(QRectF(250, 170, 440, 580), 36, 36)
    p.setBrush(QBrush(QColor("#c9d3e0")))
    for i, w in enumerate([340, 300, 340, 220, 320]):
        p.drawRoundedRect(QRectF(300, 250 + i * 70, w, 26), 13, 13)
    # hidden line revealed in red
    p.setBrush(QBrush(QColor("#e53935")))
    p.drawRoundedRect(QRectF(300, 600, 260, 26), 13, 13)
    # magnifier
    pen = QPen(QColor("#ffb300"), 56)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(560, 600), 150, 150)
    p.drawLine(QPointF(670, 710), QPointF(800, 840))
    p.end()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.save(out)
    print("icon written to", out)

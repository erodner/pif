# PyInstaller spec: one bundle with the desktop app and the `pif` command line tool.
#
#   python scripts/fetch_models.py build/models     # bundled ML model (MiniLM, 23 MB)
#   python scripts/make_icon.py build/icon.png
#   pyinstaller --noconfirm packaging/pif.spec
#
# Output: dist/Prompt Injection Finder.app (macOS) or dist/PromptInjectionFinder/ (Windows/Linux).
# The DeBERTa classifier is not bundled (740 MB); the app downloads it on request.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

ROOT = Path(SPECPATH).parent
APP_NAME = "Prompt Injection Finder"
DIR_NAME = "PromptInjectionFinder"
VERSION = next(
    line.split('"')[1] for line in (ROOT / "src/pif/__init__.py").read_text().splitlines() if line.startswith("__version__")
)

icon_png = ROOT / "build/icon.png"
icon = str(icon_png) if icon_png.exists() else None

datas = []
models = ROOT / "build/models"
if models.exists():
    datas.append((str(models), "models"))
datas += collect_data_files("rapidocr_onnxruntime")  # OCR models + config.yaml
datas += collect_data_files("pif")  # injection head weights
datas += copy_metadata("promptinjectorfinder")
datas += [(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]

binaries = collect_dynamic_libs("onnxruntime")

hiddenimports = [
    "pif.ml.cascade",
    "pif.ml.onnx_models",
    "pif.visibility.ocr",
    "tokenizers",
    "rapidocr_onnxruntime",
]
excludes = [
    "tkinter", "matplotlib", "IPython", "pytest", "torch", "tensorflow",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtTest",
]


# Not needed at runtime: PyMuPDF's optional layout-analysis models (~50 MB) and dev headers.
_DROP = ("pymupdf/layout", "pymupdf\\layout", "pymupdf/mupdf-devel", "pymupdf\\mupdf-devel")


def _keep(entry) -> bool:
    return not any(entry[0].startswith(d) for d in _DROP)


def analysis(script):
    a = Analysis(
        [str(ROOT / "packaging" / script)],
        pathex=[str(ROOT / "src")],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        excludes=excludes,
        noarchive=False,
    )
    a.datas = [d for d in a.datas if _keep(d)]
    a.binaries = [b for b in a.binaries if _keep(b)]
    return a


gui_a = analysis("entry_gui.py")
cli_a = analysis("entry_cli.py")

gui_pyz = PYZ(gui_a.pure)
cli_pyz = PYZ(cli_a.pure)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME if sys.platform == "darwin" else DIR_NAME,
    console=False,
    icon=icon,
    upx=False,
)
cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name="pif",
    console=True,
    icon=icon,
    upx=False,
)

coll = COLLECT(
    gui_exe,
    gui_a.binaries,
    gui_a.datas,
    cli_exe,
    cli_a.binaries,
    cli_a.datas,
    upx=False,
    name=DIR_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="io.github.erodner.pif",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "GNU AGPL v3 or later",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "PDF document",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "LSItemContentTypes": ["com.adobe.pdf"],
                }
            ],
        },
    )

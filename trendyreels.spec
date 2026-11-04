# PyInstaller spec: builds dist/TrendyReelsMaker.exe (one file, no console).
#   pyinstaller trendyreels.spec
import os

ROOT = os.path.abspath(os.path.dirname(SPEC))
SRC = os.path.join(ROOT, "src")
ASSETS = os.path.join(SRC, "trendyreels", "assets")

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[SRC],
    datas=[(os.path.join(ASSETS, "icon.ico"), "."), (os.path.join(ASSETS, "icon.png"), ".")],
    hiddenimports=["trendyreels.app.main_window", "trendyreels.cli", "edge_tts", "aiohttp", "certifi"],
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "tkinter", "matplotlib", "scipy", "faster_whisper", "ctranslate2", "torch",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="TrendyReelsMaker",
    icon=os.path.join(ASSETS, "icon.ico"),
    console=False,
    upx=False,
)

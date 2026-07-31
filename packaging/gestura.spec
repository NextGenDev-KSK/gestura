# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Gestura (Windows, one-folder).

Build from the repo root::

    python scripts/fetch_models.py          # ensure the model is present
    pyinstaller packaging/gestura.spec --noconfirm

Output: ``dist/Gestura/Gestura.exe`` (+ its folder). The Inno Setup script in
``packaging/gestura_installer.iss`` wraps that folder into an installer.
"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ["gestura.app.camera_view"]  # QML type registered via import side-effect

# MediaPipe ships model graphs / native libs that must be collected explicitly.
for pkg in ("mediapipe",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Bundle our QML UI and the hand-landmark model.
datas += [
    ("src/gestura/app/qml", "gestura/app/qml"),
    ("models/hand_landmarker.task", "models"),
]

a = Analysis(
    ["src/gestura/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Gestura",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed app (no console)
    icon="assets/icons/gestura.ico" if __import__("os").path.exists(
        "assets/icons/gestura.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Gestura",
)

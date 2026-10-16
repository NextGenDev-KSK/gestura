# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Gestura (Windows, one-folder).

Build from the repo root::

    python scripts/fetch_models.py          # ensure the model is present
    pyinstaller packaging/gestura.spec --noconfirm

Output: ``dist/Gestura/Gestura.exe`` (+ its folder). The Inno Setup script in
``packaging/gestura_installer.iss`` wraps that folder into an installer.
"""

import os

from PyInstaller.utils.hooks import collect_all, get_module_file_attribute

# SPECPATH is the directory holding this spec (packaging/); the repo root is its parent.
ROOT = os.path.dirname(SPECPATH)  # noqa: F821 - SPECPATH is injected by PyInstaller


def _p(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


datas = []
binaries = []
hiddenimports = ["gestura.app.camera_view"]  # QML type registered via import side-effect

# MediaPipe ships model graphs / native libs that must be collected explicitly.
for pkg in ("mediapipe",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Our QML uses Qt Quick modules (Controls.Basic, Effects, Layouts) that are loaded as *runtime*
# plugins — PyInstaller can't discover them from the .qml text, so bundle the PySide6 QML module
# tree and Qt plugins explicitly, or the frozen app's UI fails to load.
_pyside = os.path.dirname(get_module_file_attribute("PySide6"))
for _sub in ("qml", "plugins"):
    _src = os.path.join(_pyside, _sub)
    if os.path.isdir(_src):
        datas.append((_src, f"PySide6/{_sub}"))

# Bundle our QML UI, the hand-landmark model, and the window/tray icons.
datas += [
    (_p("src", "gestura", "app", "qml"), "gestura/app/qml"),
    (_p("models", "hand_landmarker.task"), "models"),
    (_p("assets", "icons"), "assets/icons"),
]

_icon = _p("assets", "icons", "gestura.ico")

a = Analysis(
    [_p("src", "gestura", "__main__.py")],
    pathex=[_p("src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter"],
    noarchive=False,
)

# Bundling the whole PySide6 qml/plugins trees (above) drags in every Qt add-on and its DLLs:
# a 196 MB web browser engine, 3D, charts, maps, multimedia + FFmpeg, PDF, SQL, serial ports, the
# virtual keyboard, every Controls style... none of which Gestura uses (its QML imports only
# QtQuick, QtQuick.Controls.Basic, QtQuick.Layouts and QtQuick.Effects). Dropping them cuts the
# download roughly in half. OpenCV's FFmpeg plugin only reads video files/streams; webcams use the
# built-in Media Foundation / DirectShow backends. If you start using one of these Qt modules,
# remove its entry here.
_UNUSED = (
    "webengine", "qtwebview", "webview", "webchannel", "websockets",
    "qt63d", "qt3d", "quick3d", "assetimporters", "sceneparsers", "renderers", "renderplugins",
    "geometryloaders", "charts", "datavisualization", "qt6graphs", "qtgraphs",
    "location", "positioning", "/position/", "multimedia", "avcodec-", "avformat-", "avutil-",
    "swresample-", "swscale-", "opencv_videoio_ffmpeg", "qt6pdf", "qtpdf", "remoteobjects",
    "scxml", "sensors", "serialbus", "serialport", "spatialaudio", "qt6sql", "sqldrivers",
    "statemachine", "qt6test", "quicktest", "qttest", "texttospeech", "virtualkeyboard",
    "qt6designer", "qmlcompiler", "qmllint", "qmltooling", "qt6lottie", "quicktimeline",
    "quickparticles", "quickdialogs2", "quickwidgets", "openglwidgets", "printsupport",
    "qt6labs", "/labs/", "qt5compat", "controls2material", "controls2universal",
    "controls2imagine", "controls2fusion", "fluentwinui3", "controls2windowsstyle",
    "/controls/material", "/controls/universal", "/controls/imagine", "/controls/fusion",
    "/controls/fluentwinui3", "/controls/windows", "pyside6/translations",
)


def _keep(entry) -> bool:
    dest = entry[0].replace("\\", "/").lower()
    return not any(token in dest for token in _UNUSED)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

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
    icon=_icon if os.path.exists(_icon) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Gestura",
)

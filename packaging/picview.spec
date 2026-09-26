"""Windows one-file EXE; macOS application bundle for DMG distribution."""

import sys
import tomllib
from pathlib import Path

root = Path(SPECPATH).parent
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
is_macos = sys.platform == "darwin"

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "src")],
    datas=[(str(root / "src" / "picview" / "assets" / "picview-icon.png"), "picview/assets")],
    # The supported entry point uses Qt, not the legacy Tk implementation.
    excludes=["tkinter", "tkinterdnd2", "customtkinter"],
)
pyz = PYZ(a.pure)
options = dict(
    name="PicView",
    console=False,
    upx=False,
    icon=str(root / "build" / ("picview.icns" if is_macos else "picview.ico")),
)
if is_macos:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    contents = COLLECT(exe, a.binaries, a.datas, name="PicView", upx=False)
    app = BUNDLE(
        contents,
        name="PicView.app",
        icon=options["icon"],
        bundle_identifier="io.github.codemee.picview",
        info_plist={
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas,
        version=str(root / "build" / "windows-version.txt"),
        **options,
    )

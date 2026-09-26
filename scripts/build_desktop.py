"""Build, smoke-test and package PicView on the target operating system."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    if sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"}:
        target = "windows-x64"
    elif sys.platform == "darwin" and platform.machine().lower() == "arm64":
        target = "macos-arm64"
    else:
        raise SystemExit("Build on Windows x64 or macOS Apple Silicon with native Python.")

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    build = ROOT / "build"
    output = ROOT / "dist" / "desktop"
    release = output / "release"
    build.mkdir(exist_ok=True)
    release.mkdir(parents=True, exist_ok=True)
    macos = sys.platform == "darwin"
    build_env = os.environ.copy()
    if not macos:
        # Avoid bundling unrelated DLLs from desktop tools on the user's PATH.
        windows = Path(os.environ["SystemRoot"])
        build_env["PATH"] = os.pathsep.join(map(str, [
            Path(sys.executable).parent, Path(sys.base_prefix),
            windows / "System32", windows,
        ]))
    with Image.open(ROOT / "src" / "picview" / "assets" / "picview-icon.png") as icon:
        icon.save(build / ("picview.icns" if macos else "picview.ico"))

    if not macos:
        numeric_version = tuple(int(part) for part in version.split(".")) + (0,)
        (build / "windows-version.txt").write_text(
            "VSVersionInfo(ffi=FixedFileInfo("
            f"filevers={numeric_version!r}, prodvers={numeric_version!r}, "
            "mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), "
            "kids=[StringFileInfo([StringTable('040904B0', ["
            "StringStruct('ProductName', 'PicView'), "
            f"StringStruct('FileVersion', {version!r}), "
            f"StringStruct('ProductVersion', {version!r})"
            "])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])",
            encoding="utf-8",
        )
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", output, "--workpath", build / "pyinstaller",
        ROOT / "packaging" / "picview.spec", cwd=ROOT, env=build_env)

    executable = output / ("PicView.app/Contents/MacOS/PicView" if macos else "PicView.exe")
    report = build / "desktop-smoke.json"
    report.unlink(missing_ok=True)
    try:
        run(executable, "--smoke-test", report, env={**build_env, "QT_QPA_PLATFORM": "offscreen"}, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if report.exists():
            print(report.read_text(encoding="utf-8"), flush=True)
        raise
    assert json.loads(report.read_text()) == {"version": version, "ok": True}
    print("Frozen application smoke test passed.", flush=True)

    artifact = release / f"PicView-{version}-{target}{'.dmg' if macos else '.exe'}"
    if macos:
        # ditto preserves the bundle's symlinks, permissions and ad-hoc signature.
        staging = build / "dmg"
        staging.mkdir(exist_ok=True)
        run("ditto", output / "PicView.app", staging / "PicView.app")
        applications = staging / "Applications"
        if not applications.is_symlink():
            applications.symlink_to("/Applications", target_is_directory=True)
        run("codesign", "--verify", "--deep", "--strict", staging / "PicView.app")
        run("hdiutil", "create", "-ov", "-format", "UDZO", "-volname", "PicView",
            "-srcfolder", staging, artifact)
        run("hdiutil", "verify", artifact)
    else:
        shutil.copy2(executable, artifact)
    with artifact.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    artifact.with_suffix(artifact.suffix + ".sha256").write_text(f"{digest}  {artifact.name}\n")
    print(f"Built {artifact}", flush=True)


if __name__ == "__main__":
    main()

"""Optional, per-user Explorer and Finder context-menu commands."""
from __future__ import annotations

import ctypes
import plistlib
import shutil
import sys
from pathlib import Path

from .utils import IMAGE_SUFFIXES


WINDOWS_VERB = "PicView.Open"
WINDOWS_OWNER = "io.github.codemee.picview"
MAC_SERVICE_NAME = "io.github.codemee.picview.open.service"
MAC_SERVICE_ID = "io.github.codemee.picview.open-service"


def windows_keys() -> tuple[tuple[str, str], ...]:
    return (
        (rf"Software\Classes\Directory\shell\{WINDOWS_VERB}", "%1"),
        (rf"Software\Classes\Directory\Background\shell\{WINDOWS_VERB}", "%V"),
        *((rf"Software\Classes\SystemFileAssociations\{suffix}\shell\{WINDOWS_VERB}", "%1")
          for suffix in sorted(IMAGE_SUFFIXES)),
    )


def windows_command(placeholder: str) -> str:
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        prefix = f'"{executable}"'
    else:
        pythonw = executable.with_name("pythonw.exe")
        prefix = f'"{pythonw if pythonw.is_file() else executable}" -m picview'
    return f'{prefix} "{placeholder}"'


def windows_icon() -> str:
    if getattr(sys, "frozen", False):
        return f"{sys.executable},0"
    return str(Path(__file__).parent / "assets" / "picview-icon.ico")


def _windows_owned(key_path: str) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, "PicViewOwner")[0] == WINDOWS_OWNER
    except FileNotFoundError:
        return False


def windows_enabled() -> bool:
    return all(_windows_owned(path) for path, _ in windows_keys())


def _remove_windows_key(key_path: str) -> None:
    import winreg

    if not _windows_owned(key_path): return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
    except FileNotFoundError:
        pass
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)


def _refresh_windows_shell() -> None:
    from ctypes import wintypes

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHChangeNotify.argtypes = [wintypes.LONG, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p]
    shell.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED / SHCNF_IDLIST


def set_windows_enabled(enabled: bool, label: str) -> None:
    import winreg

    entries = windows_keys()
    if enabled:
        # The verb is unique to PicView. Never overwrite a key owned by another app.
        for key_path, _ in entries:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                continue
            with key:
                if not _windows_owned(key_path):
                    raise OSError(f"Registry key belongs to another application: {key_path}")
        try:
            for key_path, placeholder in entries:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
                    winreg.SetValueEx(key, "PicViewOwner", 0, winreg.REG_SZ, WINDOWS_OWNER)
                    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, label)
                    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, windows_icon())
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path + r"\command") as command:
                    winreg.SetValueEx(command, "", 0, winreg.REG_SZ, windows_command(placeholder))
        except OSError:
            for key_path, _ in entries:
                _remove_windows_key(key_path)
            raise
    else:
        for key_path, _ in entries:
            _remove_windows_key(key_path)
    _refresh_windows_shell()


def mac_service_source() -> Path:
    if not getattr(sys, "frozen", False): return Path()
    return Path(sys.executable).resolve().parents[1] / "PlugIns" / "PicViewOpen.service"


def mac_service_destination() -> Path:
    return Path.home() / "Library" / "Services" / MAC_SERVICE_NAME


def mac_available() -> bool:
    if not getattr(sys, "frozen", False): return False
    source = mac_service_source() / "Contents"
    return (source / "Info.plist").is_file() and (source / "MacOS" / "PicViewOpenService").is_file()


def mac_enabled() -> bool:
    try:
        info = plistlib.loads((mac_service_destination() / "Contents" / "Info.plist").read_bytes())
        return info.get("CFBundleIdentifier") == MAC_SERVICE_ID
    except (OSError, ValueError, TypeError):
        return False


def _refresh_mac_services() -> None:
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit").NSUpdateDynamicServices()


def set_mac_enabled(enabled: bool) -> None:
    destination = mac_service_destination()
    services = destination.parent.resolve()
    if destination.resolve().parent != services:
        raise OSError("Invalid Finder Services destination")
    if enabled:
        if not mac_available(): raise OSError("Finder integration requires the packaged PicView.app")
        if destination.exists() and not mac_enabled():
            raise OSError(f"Finder Service belongs to another application: {destination}")
        services.mkdir(parents=True, exist_ok=True)
        if not destination.exists(): shutil.copytree(mac_service_source(), destination)
    elif mac_enabled():
        shutil.rmtree(destination)
    _refresh_mac_services()


def available() -> bool:
    if sys.platform == "win32": return True
    if sys.platform == "darwin": return mac_available()
    return False


def enabled() -> bool:
    if sys.platform == "win32": return windows_enabled()
    if sys.platform == "darwin": return mac_enabled()
    return False


def set_enabled(value: bool, label: str) -> None:
    if sys.platform == "win32": set_windows_enabled(value, label)
    elif sys.platform == "darwin": set_mac_enabled(value)
    else: raise OSError("Explorer/Finder integration is unavailable on this platform")

import importlib.util
import plistlib
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from picview import qt_app, shell_integration
from test_tabs import browser


def fake_registry():
    data = {}
    registry = types.ModuleType("winreg")
    registry.HKEY_CURRENT_USER = object()
    registry.REG_SZ = 1

    class Key:
        def __init__(self, path): self.path = path
        def __enter__(self): return self
        def __exit__(self, *args): return False

    def open_key(root, path):
        if path not in data: raise FileNotFoundError(path)
        return Key(path)

    def create_key(root, path):
        data.setdefault(path, {})
        return Key(path)

    def query_value(key, name):
        if name not in data[key.path]: raise FileNotFoundError(name)
        return data[key.path][name], registry.REG_SZ

    def set_value(key, name, reserved, kind, value):
        data[key.path][name] = value

    def delete_key(root, path):
        if path not in data: raise FileNotFoundError(path)
        if any(item.startswith(path + "\\") for item in data): raise OSError("Has subkeys")
        del data[path]

    registry.OpenKey = open_key
    registry.CreateKeyEx = create_key
    registry.QueryValueEx = query_value
    registry.SetValueEx = set_value
    registry.DeleteKey = delete_key
    return registry, data


def test_windows_context_commands_cover_folders_and_supported_images(monkeypatch, tmp_path):
    registry, data = fake_registry()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    refreshed = []
    monkeypatch.setattr(shell_integration, "_refresh_windows_shell", lambda: refreshed.append(True))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "PicView.exe"))
    entries = shell_integration.windows_keys()
    assert len(entries) == len(shell_integration.IMAGE_SUFFIXES) + 2
    assert any("Directory\\Background" in key and argument == "%V" for key, argument in entries)
    assert not shell_integration.windows_enabled()
    shell_integration.set_windows_enabled(True, "Open in PicView")
    assert shell_integration.windows_enabled()
    for key, argument in entries:
        assert data[key]["PicViewOwner"] == shell_integration.WINDOWS_OWNER
        assert data[key]["MUIVerb"] == "Open in PicView"
        assert data[key]["Icon"] == f"{tmp_path / 'PicView.exe'},0"
        assert data[key + "\\command"][""] == f'"{tmp_path / "PicView.exe"}" "{argument}"'
    shell_integration.set_windows_enabled(False, "Open in PicView")
    assert not data
    assert refreshed == [True, True]


def test_source_windows_icon_is_bundled_ico(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert Path(shell_integration.windows_icon()).is_file()
    assert Path(shell_integration.windows_icon()).suffix == ".ico"


def test_windows_registration_never_overwrites_an_unowned_verb(monkeypatch):
    registry, data = fake_registry()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(shell_integration, "_refresh_windows_shell", lambda: None)
    key = shell_integration.windows_keys()[0][0]
    data[key] = {"MUIVerb": "Something else"}
    with pytest.raises(OSError, match="another application"):
        shell_integration.set_windows_enabled(True, "Open in PicView")
    assert data[key] == {"MUIVerb": "Something else"}


def test_finder_service_toggle_copies_only_picview_bundle(tmp_path, monkeypatch):
    source = tmp_path / "packaged" / "PicViewOpen.service"
    info_path = source / "Contents" / "Info.plist"
    info_path.parent.mkdir(parents=True)
    info_path.write_bytes(plistlib.dumps({"CFBundleIdentifier": shell_integration.MAC_SERVICE_ID}))
    destination = tmp_path / "Library" / "Services" / shell_integration.MAC_SERVICE_NAME
    refreshed = []
    monkeypatch.setattr(shell_integration, "mac_available", lambda: True)
    monkeypatch.setattr(shell_integration, "mac_service_source", lambda: source)
    monkeypatch.setattr(shell_integration, "mac_service_destination", lambda: destination)
    monkeypatch.setattr(shell_integration, "_refresh_mac_services", lambda: refreshed.append(True))
    shell_integration.set_mac_enabled(True)
    assert shell_integration.mac_enabled()
    assert destination.joinpath("Contents", "Info.plist").is_file()
    shell_integration.set_mac_enabled(False)
    assert not destination.exists()
    assert refreshed == [True, True]


def test_finder_toggle_preserves_an_unowned_service(tmp_path, monkeypatch):
    destination = tmp_path / "Library" / "Services" / shell_integration.MAC_SERVICE_NAME
    info = destination / "Contents" / "Info.plist"
    info.parent.mkdir(parents=True)
    info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "example.other-app"}))
    monkeypatch.setattr(shell_integration, "mac_available", lambda: True)
    monkeypatch.setattr(shell_integration, "mac_service_destination", lambda: destination)
    monkeypatch.setattr(shell_integration, "_refresh_mac_services", lambda: None)
    with pytest.raises(OSError, match="another application"):
        shell_integration.set_mac_enabled(True)
    shell_integration.set_mac_enabled(False)
    assert info.is_file()


def test_mac_desktop_build_declares_finder_service(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts" / "build_desktop.py"
    spec = importlib.util.spec_from_file_location("build_desktop", source)
    build_desktop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_desktop)

    commands = []
    monkeypatch.setattr(build_desktop, "run", lambda *args, **kwargs: commands.append(args))
    app = tmp_path / "PicView.app"
    build_desktop.bundle_finder_service(app)
    service = app / "Contents" / "PlugIns" / "PicViewOpen.service"
    info = plistlib.loads((service / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == shell_integration.MAC_SERVICE_ID
    assert info["NSServices"][0]["NSSendFileTypes"] == ["public.folder", "public.image"]
    assert info["NSServices"][0]["NSRequiredContext"] == {}
    assert commands[0][0] == "clang"
    assert commands[-1][:3] == ("codesign", "--force", "--deep")


def test_startup_paths_open_folders_and_select_images(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    image = folder / "image.png"
    Image.new("RGB", (10, 10)).save(image)
    other = folder / "notes.txt"
    other.write_text("skip", encoding="utf-8")
    opened = []
    window = types.SimpleNamespace(open_folder=lambda path, selected=None: opened.append((path, selected)))
    qt_app.open_startup_paths(window, [str(folder), str(image), str(other), str(folder / "missing")])
    assert opened == [(folder, None), (folder, image)]


def test_open_folder_dialog_starts_from_current_folders_parent(browser, monkeypatch):
    window, folders = browser
    window.open_folder(folders[0])
    initial = []
    monkeypatch.setattr(qt_app.QFileDialog, "getExistingDirectory",
                        lambda _parent, _title, path: initial.append(path) or "")
    window.choose()
    assert initial == [str(folders[0].parent)]


def test_toolbar_button_can_toggle_shell_integration(browser, monkeypatch):
    window, _ = browser
    state = {"enabled": False}
    monkeypatch.setattr(shell_integration, "available", lambda: True)
    monkeypatch.setattr(shell_integration, "enabled", lambda: state["enabled"])
    monkeypatch.setattr(shell_integration, "set_enabled", lambda value, label: state.update(enabled=value))
    window.refresh_shell_integration_button()
    assert not window.integration_button.isChecked()
    window.integration_button.click()
    assert state["enabled"] and window.integration_button.isChecked()
    window.integration_button.click()
    assert not state["enabled"] and not window.integration_button.isChecked()
    window.toggle_lang()
    label = "finder_integration" if sys.platform == "darwin" else "shell_integration"
    assert window.t[label] in window.integration_button.toolTip()

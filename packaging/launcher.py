"""Standalone GUI entry point and frozen-application smoke check."""

import sys


def smoke_test(report_path):
    import json
    import tempfile
    from pathlib import Path

    from PIL import Image
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QFileOpenEvent

    from picview import __version__, qt_app, shell_integration
    from picview.settings import DEFAULT_SETTINGS

    license_path = (Path(sys._MEIPASS) / "licenses" / "LICENSE" if getattr(sys, "frozen", False)
                    else Path(__file__).resolve().parents[1] / "LICENSE")
    assert "GNU GENERAL PUBLIC LICENSE" in license_path.read_text(encoding="utf-8"), "Bundled license is missing"

    # Keep validation independent of the user's saved folders and preferences.
    qt_app.load_settings = lambda: DEFAULT_SETTINGS.copy()
    qt_app.save_settings = lambda values: None
    app = qt_app.PicViewApplication([])
    qt_app.set_application_identity(app)
    assert app.applicationName() == "PicView"
    assert not app.windowIcon().pixmap(32, 32).isNull(), "Bundled application icon could not be loaded"
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory).resolve()
        sample = folder / "sample.png"
        Image.new("RGB", (64, 48), "red").save(sample)
        window = qt_app.PicView()
        assert window.windowIcon().cacheKey() == app.windowIcon().cacheKey()
        if sys.platform == "darwin" and getattr(sys, "frozen", False):
            assert shell_integration.mac_available(), "Bundled Finder Service is missing"
        window.show()
        app.sendEvent(app, QFileOpenEvent(str(sample)))
        app.set_open_paths_handler(lambda paths: qt_app.open_received_paths(window, paths))
        app.processEvents()
        assert window.folder == folder, "Document-open request failed"
        assert window.thumbs.selected_path == sample, "Requested image was not selected"
        assert window.image.frames, "Image decoder failed"
        assert not window.image.label.pixmap().isNull(), "Qt failed to render image"
        assert f"v{__version__}" in window.windowTitle()
        vector = folder / "vector.svg"
        vector.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><rect x="10" y="10" width="30" height="20" fill="red"/></svg>', encoding="utf-8")
        app.sendEvent(app, QFileOpenEvent(str(vector)))
        app.processEvents()
        assert window.thumbs.selected_path == vector, "Running application did not open the requested image"
        assert window.image.frames, "Bundled SVG renderer failed to load"
        window.image.choose_zoom(2000)
        window.image.rotate()
        assert not window.image.label.pixmap().isNull(), "SVG rendering failed"
        mime = QMimeData()
        mime.setData(qt_app.COMPARISON_TAB_MIME, str(id(window.pages()[0])).encode("ascii"))
        assert window.add_comparison_drop(window.image, mime), "SVG comparison drop failed"
        app.processEvents()
        assert len(window.comparison_area.pages) == 2, "SVG comparison failed"
        window.show_about()
        app.processEvents()
        assert "GPL-3.0-or-later" in window.about_dialog.license_label.text(), "About license identifier is missing"
        assert "GNU GENERAL PUBLIC LICENSE" in window.about_dialog.license_view.toPlainText(), "About license text is missing"
        window.about_dialog.close()
        window.close()
        app.processEvents()
    Path(report_path).write_text(json.dumps({"version": __version__, "ok": True}))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        try:
            smoke_test(sys.argv[2])
        except Exception:
            import traceback
            from pathlib import Path

            Path(sys.argv[2]).write_text(traceback.format_exc(), encoding="utf-8")
            sys.exit(1)
    else:
        from picview.entrypoint import main

        main()

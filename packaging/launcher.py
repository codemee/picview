"""Standalone GUI entry point and frozen-application smoke check."""

import sys


def smoke_test(report_path):
    import json
    import tempfile
    from pathlib import Path

    from PIL import Image
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from picview import __version__, qt_app
    from picview.settings import DEFAULT_SETTINGS

    # Keep validation independent of the user's saved folders and preferences.
    qt_app.load_settings = lambda: DEFAULT_SETTINGS.copy()
    qt_app.save_settings = lambda values: None
    app = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        sample = folder / "sample.png"
        Image.new("RGB", (64, 48), "red").save(sample)
        window = qt_app.PicView()
        icon_path = Path(qt_app.__file__).parent / "assets" / "picview-icon.png"
        icon = QIcon(str(icon_path))
        assert not icon.pixmap(32, 32).isNull(), "Bundled icon could not be loaded"
        window.setWindowIcon(icon)
        window.show()
        window.open_folder(folder)
        app.processEvents()
        assert window.image.frames, "Image decoder failed"
        assert not window.image.label.pixmap().isNull(), "Qt failed to render image"
        assert f"v{__version__}" in window.windowTitle()
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
        from picview.qt_app import main

        main()

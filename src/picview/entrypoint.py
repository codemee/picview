"""Forward file opens before importing the image viewer and Qt Widgets."""

import sys


def main() -> None:
    paths = sys.argv[1:]
    if paths and all(not path.startswith("-") for path in paths):
        from .instance import forward_paths_early

        if forward_paths_early(paths):
            return

    from .qt_app import main as show_viewer

    show_viewer()

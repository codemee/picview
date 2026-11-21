"""Keep the real desktop launcher compatible with unsaved-change prompts."""
import json
import os
from pathlib import Path
import subprocess
import sys

from picview import __version__


def test_source_desktop_smoke_closes_without_dialog(tmp_path):
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "smoke.json"
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "APPDATA": str(tmp_path / "settings"),
                   "PYTHONPATH": str(root / "src")}
    result = subprocess.run([sys.executable, str(root / "packaging/launcher.py"), "--smoke-test", str(report)],
                            env=environment, cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(report.read_text()) == {"version": __version__, "ok": True}

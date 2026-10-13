from picview.settings import DEFAULT_SETTINGS, load_settings, save_settings


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "PicView" / "settings.json"
    save_settings({"folder": "C:/Pictures", "thumbnail_size": 200, "theme": "dark", "unexpected": "ignored"}, path)
    loaded = load_settings(path)
    assert loaded["folder"] == "C:/Pictures"
    assert loaded["thumbnail_size"] == 200
    assert loaded["theme"] == "dark"
    assert "unexpected" not in loaded


def test_invalid_settings_fall_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_settings(path) == DEFAULT_SETTINGS


def test_invalid_tab_records_and_values_are_sanitized(tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"tabs": [None, {"folder": 3}, {"folder": "C:/Pictures", "thumbnail_size": "large", "image_zoom": float("nan"), "orientation": "invalid", "selected_file": 7}], "active_tab": 99}, path)
    loaded = load_settings(path)
    assert len(loaded["tabs"]) == 1
    assert loaded["tabs"][0]["thumbnail_size"] == 140
    assert loaded["tabs"][0]["image_zoom"] == 1
    assert loaded["tabs"][0]["selected_file"] == ""
    assert loaded["tabs"][0]["orientation"] == "vertical"
    assert loaded["active_tab"] == 0

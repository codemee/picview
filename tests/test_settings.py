from picview.settings import DEFAULT_SETTINGS, load_settings, save_settings


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "PicView" / "settings.json"
    save_settings({"folder": "C:/Pictures", "thumbnail_size": 200, "unexpected": "ignored"}, path)
    loaded = load_settings(path)
    assert loaded["folder"] == "C:/Pictures"
    assert loaded["thumbnail_size"] == 200
    assert "unexpected" not in loaded


def test_invalid_settings_fall_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_settings(path) == DEFAULT_SETTINGS

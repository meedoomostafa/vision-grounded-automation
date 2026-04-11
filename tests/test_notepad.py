import pytest

from src.automation import notepad
from src.core.exceptions import WindowNotFoundError


def test_save_post_raises_when_file_is_not_written(monkeypatch, tmp_path):
    monkeypatch.setattr(notepad.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(notepad.config, "SAVE_DIALOG_TIMEOUT", 1)
    monkeypatch.setattr(notepad.time, "sleep", lambda *_: None)

    monkeypatch.setattr(notepad, "hotkey", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "type_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "press", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "wait_for_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "activate_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "is_window_open", lambda *args, **kwargs: False)

    with pytest.raises(WindowNotFoundError):
        notepad.save_post(7)


def test_save_post_accepts_updated_file(monkeypatch, tmp_path):
    target = tmp_path / "post_8.txt"
    target.write_text("old")
    previous_mtime = target.stat().st_mtime_ns

    monkeypatch.setattr(notepad.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(notepad.config, "SAVE_DIALOG_TIMEOUT", 1)
    monkeypatch.setattr(notepad.time, "sleep", lambda *_: None)

    monkeypatch.setattr(notepad, "hotkey", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "type_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "press", lambda *args, **kwargs: target.write_text("new"))
    monkeypatch.setattr(notepad, "wait_for_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "activate_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "is_window_open", lambda *args, **kwargs: False)

    notepad.save_post(8)
    assert target.read_text() == "new"
    assert target.stat().st_mtime_ns != previous_mtime

import pytest

from src.automation import notepad
from src.core.exceptions import WindowNotFoundError


def test_save_post_raises_when_file_is_not_written(monkeypatch, tmp_path):
    monkeypatch.setattr(notepad.config, "DRY_RUN", False)
    monkeypatch.setattr(notepad.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(notepad.config, "SAVE_DIALOG_TIMEOUT", 1)

    monkeypatch.setattr(notepad, "hotkey", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "type_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "press", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "wait_ms", lambda *_: None)
    monkeypatch.setattr(notepad, "_fill_save_path_with_pywinauto", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(notepad, "_wait_for_saved_file", lambda *args, **kwargs: False)
    monkeypatch.setattr(notepad, "wait_for_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "activate_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "is_window_open", lambda *args, **kwargs: False)

    with pytest.raises(WindowNotFoundError):
        notepad.save_post(7)


def test_save_post_accepts_updated_file(monkeypatch, tmp_path):
    monkeypatch.setattr(notepad.config, "DRY_RUN", False)
    target = tmp_path / "post_8.txt"
    target.write_text("old")
    previous_mtime = target.stat().st_mtime_ns

    monkeypatch.setattr(notepad.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(notepad.config, "SAVE_DIALOG_TIMEOUT", 1)

    monkeypatch.setattr(notepad, "hotkey", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "type_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "wait_ms", lambda *_: None)
    monkeypatch.setattr(notepad, "_fill_save_path_with_pywinauto", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(notepad, "press", lambda *args, **kwargs: target.write_text("new content"))
    monkeypatch.setattr(notepad, "wait_for_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "activate_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "is_window_open", lambda *args, **kwargs: False)

    notepad.save_post(8)

    assert target.read_text() == "new content"
    assert target.stat().st_mtime_ns != previous_mtime or target.stat().st_size != len("old")


def test_save_post_returns_success_when_file_is_written_even_if_dialog_lingers(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(notepad.config, "DRY_RUN", False)
    monkeypatch.setattr(notepad.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(notepad.config, "SAVE_DIALOG_TIMEOUT", 1)

    dismissed = []
    save_window_states = iter([True])

    monkeypatch.setattr(notepad, "hotkey", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "type_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "press", lambda key: dismissed.append(key))
    monkeypatch.setattr(notepad, "wait_ms", lambda *_: None)
    monkeypatch.setattr(notepad, "_fill_save_path_with_pywinauto", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(notepad, "wait_for_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "activate_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "_wait_for_saved_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        notepad,
        "is_window_open",
        lambda title: next(save_window_states)
        if (title == "Save" or (isinstance(title, tuple) and "Save" in title))
        else False,
    )

    notepad.save_post(9)

    assert dismissed == ["enter", "esc"]


def test_save_post_focuses_file_name_field_before_typing(monkeypatch, tmp_path):
    monkeypatch.setattr(notepad.config, "DRY_RUN", False)
    monkeypatch.setattr(notepad.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(notepad.config, "SAVE_DIALOG_TIMEOUT", 1)

    hotkeys = []
    typed = []

    monkeypatch.setattr(notepad, "hotkey", lambda *keys: hotkeys.append(keys))
    monkeypatch.setattr(notepad, "type_text", lambda text, **kwargs: typed.append(text))
    monkeypatch.setattr(notepad, "press", lambda *args, **kwargs: None)
    monkeypatch.setattr(notepad, "wait_ms", lambda *_: None)
    monkeypatch.setattr(notepad, "_fill_save_path_with_pywinauto", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(notepad, "_wait_for_saved_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "wait_for_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "activate_window", lambda *args, **kwargs: True)
    monkeypatch.setattr(notepad, "is_window_open", lambda *args, **kwargs: False)

    notepad.save_post(10)

    assert ("ctrl", "a") in hotkeys
    assert typed == [str((tmp_path / "post_10.txt").resolve())]

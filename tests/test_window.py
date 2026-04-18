from types import SimpleNamespace

from src.automation import window


def test_wait_for_window_uses_internal_lookup(monkeypatch):
    calls = []
    monkeypatch.setattr(window.config, "DRY_RUN", False)

    def fake_find(title_contains, timeout_ms):
        calls.append((title_contains, timeout_ms))
        return SimpleNamespace(window_text=lambda: "Untitled - Notepad")

    monkeypatch.setattr(window, "_find_window", fake_find)

    assert window.wait_for_window("Notepad", timeout=1) is True
    assert calls == [("Notepad", 1000)]


def test_activate_window_restores_and_focuses_wrapper(monkeypatch):
    monkeypatch.setattr(window.config, "DRY_RUN", False)
    restored = []
    focused = []

    class FakeWindow:
        def wrapper_object(self):
            return self

        def is_minimized(self):
            return True

        def restore(self):
            restored.append(True)

        def set_focus(self):
            focused.append(True)

        def window_text(self):
            return "post_1.txt - Notepad"

    monkeypatch.setattr(window, "_find_window", lambda *args, **kwargs: FakeWindow())
    monkeypatch.setattr(window, "wait_ms", lambda *_: None)

    assert window.activate_window("Notepad") is True
    assert restored == [True]
    assert focused == [True]


def test_is_window_open_returns_false_when_lookup_fails(monkeypatch):
    monkeypatch.setattr(window.config, "DRY_RUN", False)
    monkeypatch.setattr(
        window,
        "_find_window",
        lambda *args, **kwargs: (_ for _ in ()).throw(LookupError("missing")),
    )

    assert window.is_window_open("Confirm") is False


def test_terminal_notification_window_is_rejected_for_matching():
    assert (
        window._is_terminal_notification_window(
            "[Terminal ... notification: command completed with exit code 0]",
            "code.exe",
        )
        is True
    )


def test_regular_notepad_window_is_not_rejected_as_terminal_notification():
    assert (
        window._is_terminal_notification_window(
            "post_1.txt - Notepad",
            "notepad.exe",
        )
        is False
    )

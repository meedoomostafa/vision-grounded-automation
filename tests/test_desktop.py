from src.automation import desktop


def test_show_desktop_uses_windows_minimize_shortcut(monkeypatch):
    calls = []

    class FakeGui:
        def hotkey(self, *keys):
            calls.append(keys)

    monkeypatch.setattr(desktop.config, "DRY_RUN", False)
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(desktop, "_require_pyautogui", lambda: FakeGui())
    monkeypatch.setattr(desktop.time, "sleep", lambda *_: None)

    desktop.show_desktop()

    assert calls == [("win", "m")]


def test_show_desktop_is_noop_in_dry_run(monkeypatch):
    monkeypatch.setattr(desktop.config, "DRY_RUN", True)
    monkeypatch.setattr(
        desktop,
        "_require_pyautogui",
        lambda: (_ for _ in ()).throw(AssertionError("pyautogui should not be used in DRY_RUN")),
    )
    desktop.show_desktop()

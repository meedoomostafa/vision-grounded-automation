from src.automation import desktop


def test_show_desktop_uses_windows_minimize_shortcut(monkeypatch):
    calls = []
    waits = []

    monkeypatch.setattr(desktop.config, "DRY_RUN", False)
    monkeypatch.setattr(desktop.config, "SETTLE_DELAY", 0.25)
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(desktop, "hotkey", lambda *keys: calls.append(keys))
    monkeypatch.setattr(
        desktop,
        "wait_ms",
        lambda milliseconds: waits.append(milliseconds),
    )

    desktop.show_desktop()

    assert calls == [("win", "m")]
    assert waits == [250]


def test_show_desktop_is_noop_in_dry_run(monkeypatch):
    monkeypatch.setattr(desktop.config, "DRY_RUN", True)
    monkeypatch.setattr(
        desktop,
        "hotkey",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("hotkey should not be used in DRY_RUN")
        ),
    )

    desktop.show_desktop()

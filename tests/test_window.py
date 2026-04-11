from types import SimpleNamespace

from src.automation import window


def test_wait_for_window_uses_contains_matching(monkeypatch):
    calls = []
    monkeypatch.setattr(window.config, "DRY_RUN", False)

    fake_re = SimpleNamespace(CONTAINS="contains", IGNORECASE="ignorecase")

    def fake_get_windows(title, condition=None, flags=None):
        calls.append((title, condition, flags))
        return [SimpleNamespace(title="Untitled - Notepad", isActive=True, isVisible=True)]

    monkeypatch.setattr(
        window,
        "pywinctl",
        SimpleNamespace(Re=fake_re, getWindowsWithTitle=fake_get_windows),
    )

    assert window.wait_for_window("Notepad", timeout=1) is True
    assert calls == [("Notepad", "contains", "ignorecase")]


def test_activate_window_picks_active_visible_best_match(monkeypatch):
    activated = []
    restored = []
    monkeypatch.setattr(window.config, "DRY_RUN", False)

    class FakeWindow:
        def __init__(self, title, is_active, is_visible, minimized=False):
            self.title = title
            self.isActive = is_active
            self.isVisible = is_visible
            self.isMinimized = minimized

        def restore(self):
            restored.append(self.title)
            self.isMinimized = False

        def activate(self):
            activated.append(self.title)

    fake_re = SimpleNamespace(CONTAINS="contains", IGNORECASE="ignorecase")
    windows = [
        FakeWindow("Untitled - Notepad", is_active=False, is_visible=True),
        FakeWindow("post_1.txt - Notepad", is_active=True, is_visible=True),
    ]

    monkeypatch.setattr(
        window,
        "pywinctl",
        SimpleNamespace(Re=fake_re, getWindowsWithTitle=lambda *args, **kwargs: windows),
    )

    assert window.activate_window("Notepad") is True
    assert restored == []
    assert activated == ["post_1.txt - Notepad"]

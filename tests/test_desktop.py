from src.automation import desktop


class _FakeBot:
    def __init__(self, x: int = 100, y: int = 200):
        self.x = x
        self.y = y
        self.clicks: list[tuple[int, int]] = []
        self.moves: list[tuple[int, int]] = []
        self.waits: list[int] = []

    def click_at(self, x: int, y: int) -> None:
        self.clicks.append((x, y))
        self.x = x
        self.y = y

    def get_last_x(self) -> int:
        return self.x

    def get_last_y(self) -> int:
        return self.y

    def mouse_move(self, x: int, y: int) -> None:
        self.moves.append((x, y))
        self.x = x
        self.y = y

    def wait(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


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


def test_click_restores_cursor_when_enabled(monkeypatch):
    bot = _FakeBot(320, 240)
    restored: list[tuple[int, int]] = []
    monkeypatch.setattr(desktop.config, "DRY_RUN", False)
    monkeypatch.setattr(desktop, "get_bot", lambda: bot)
    monkeypatch.setattr(desktop, "get_cursor_position", lambda **_: (320, 240))
    monkeypatch.setattr(desktop, "move_cursor", lambda x, y: restored.append((x, y)))
    monkeypatch.setattr(desktop.execution_gate, "wait_if_paused", lambda: None)

    desktop.click(900, 500, restore_cursor=True)

    assert bot.clicks == [(900, 500)]
    assert restored == [(320, 240)]


def test_double_click_restores_cursor_when_enabled(monkeypatch):
    bot = _FakeBot(400, 260)
    restored: list[tuple[int, int]] = []
    monkeypatch.setattr(desktop.config, "DRY_RUN", False)
    monkeypatch.setattr(desktop, "get_bot", lambda: bot)
    monkeypatch.setattr(desktop, "get_cursor_position", lambda **_: (400, 260))
    monkeypatch.setattr(desktop, "move_cursor", lambda x, y: restored.append((x, y)))
    monkeypatch.setattr(desktop.execution_gate, "wait_if_paused", lambda: None)

    desktop.double_click(910, 520, restore_cursor=True)

    assert bot.clicks == [(910, 520), (910, 520)]
    assert bot.waits == [80]
    assert restored == [(400, 260)]

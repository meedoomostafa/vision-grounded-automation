from types import SimpleNamespace

from src.automation.control import ExecutionGate
from src.watcher.focus import FocusEvent, FocusWatcher


def test_focus_watcher_ignores_blacklisted_process():
    gate = ExecutionGate()
    gate.arm(["Notepad"])
    handled = []
    watcher = FocusWatcher(gate, handled.append, debounce_seconds=5.0, poll_interval=0.01)

    event = FocusEvent(
        hwnd=1,
        pid=10,
        title="Visual Studio Code",
        class_name="Chrome_WidgetWin_1",
        process_name="code.exe",
        timestamp=1.0,
    )

    watcher._last_signature = None
    watcher._last_trigger_at = 0.0
    watcher._snapshot_foreground_window = lambda: event
    wait_values = iter([False, True])
    watcher._stop_event = SimpleNamespace(
        wait=lambda _: next(wait_values),
        set=lambda: None,
    )

    watcher.run()

    assert handled == []


def test_focus_watcher_debounces_repeat_popup_events(monkeypatch):
    gate = ExecutionGate()
    gate.arm(["Notepad"])
    handled = []
    watcher = FocusWatcher(gate, handled.append, debounce_seconds=5.0, poll_interval=0.01)

    popup = FocusEvent(
        hwnd=50,
        pid=999,
        title="Security Warning",
        class_name="#32770",
        process_name="securityhealth.exe",
        timestamp=1.0,
    )
    events = iter([popup, popup])

    watcher._snapshot_foreground_window = lambda: next(events, popup)
    wait_values = iter([False, False, True])
    watcher._stop_event = SimpleNamespace(wait=lambda _: next(wait_values), set=lambda: None)
    monotonic_values = iter([10.0, 12.0])
    monkeypatch.setattr("src.watcher.focus.time.monotonic", lambda: next(monotonic_values))

    watcher.run()

    assert handled == [popup]


def test_focus_watcher_detects_dialog_class_popup():
    event = FocusEvent(
        hwnd=3,
        pid=15,
        title="Unexpected Prompt",
        class_name="#32770",
        process_name="other.exe",
        timestamp=2.0,
    )

    assert FocusWatcher._looks_like_popup(event) is True

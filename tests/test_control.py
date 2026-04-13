from src.automation.control import ExecutionGate


def test_execution_gate_expected_title_matching():
    gate = ExecutionGate()
    gate.arm(["Notepad", "Save"])

    assert gate.is_armed is True
    assert gate.is_expected_title("Untitled - Notepad") is True
    assert gate.is_expected_title("Save As") is True
    assert gate.is_expected_title("Calculator") is False


def test_execution_gate_bypass_pause_allows_actions_while_paused():
    gate = ExecutionGate()
    gate.pause("test")

    observed = []
    with gate.bypass_pause():
        gate.wait_if_paused()
        observed.append("continued")

    gate.resume("done")
    assert observed == ["continued"]

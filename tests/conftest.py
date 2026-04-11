
import pytest


@pytest.fixture(autouse=True)
def _force_dry_run(monkeypatch):
    """Ensure all tests run with DRY_RUN=true to prevent real actions."""
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("VISUAL_DEBUG", "false")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")

    # Reload config to pick up patched env
    import src.config as cfg
    monkeypatch.setattr(cfg, "DRY_RUN", True)
    monkeypatch.setattr(cfg, "VISUAL_DEBUG", False)
    monkeypatch.setattr(cfg, "GOOGLE_API_KEY", "test-key-not-real")

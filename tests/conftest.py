import pytest

from src.core.key_manager import RoundRobinKeyManager


@pytest.fixture(autouse=True)
def _force_dry_run(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("VISUAL_DEBUG", "false")
    monkeypatch.setenv("AI__Gemini__ApiKeys__0", "test-key-not-real")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")

    import src.config as cfg

    monkeypatch.setattr(cfg, "DRY_RUN", True)
    monkeypatch.setattr(cfg, "VISUAL_DEBUG", False)
    monkeypatch.setattr(cfg, "GOOGLE_API_KEY", "test-key-not-real")
    monkeypatch.setattr(cfg, "GEMINI_API_KEYS", ("test-key-not-real",))
    monkeypatch.setattr(
        cfg,
        "GEMINI_KEY_MANAGER",
        RoundRobinKeyManager(cfg.GEMINI_API_KEYS),
    )

import logging

from src.core import logger as logger_module


def test_setup_logging_writes_to_configured_logs_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(logger_module.config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(logger_module.config, "LOG_LEVEL", "INFO")

    logger_module.setup_logging(force=True)
    logging.getLogger("tests.logger").info("batch-one-log-check")

    log_file = logger_module.config.LOGS_DIR / "automation.log"
    assert log_file.exists()
    assert "batch-one-log-check" in log_file.read_text(encoding="utf-8")

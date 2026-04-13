from src import main as app_main
from src.core import logger as logger_module


def _build_posts(count: int) -> list[dict]:
    return [
        {
            "id": index,
            "title": f"Post {index}",
            "body": f"Body {index}",
        }
        for index in range(1, count + 1)
    ]


def test_main_dry_run_e2e(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"
    sample_posts = _build_posts(10)

    monkeypatch.setattr(app_main.config, "DRY_RUN", True)
    monkeypatch.setattr(app_main.config, "VISUAL_DEBUG", False)
    monkeypatch.setattr(app_main.config, "API_POSTS_LIMIT", 10)
    monkeypatch.setattr(app_main.config, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(app_main.config, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(app_main.config, "LOCK_FILE", tmp_path / ".automation.lock")
    monkeypatch.setattr(app_main, "fetch_posts", lambda limit: sample_posts[:limit])
    monkeypatch.setattr(
        app_main,
        "setup_logging",
        lambda: logger_module.setup_logging(force=True),
    )

    app_main.main()

    created_files = sorted(output_dir.glob("post_*.txt"))
    assert len(created_files) == 10
    assert created_files[0].read_text(encoding="utf-8").startswith("DRY_RUN placeholder")

    log_file = logs_dir / "automation.log"
    assert log_file.exists()
    log_text = log_file.read_text(encoding="utf-8")
    assert "Complete: 10 succeeded, 0 failed out of 10" in log_text

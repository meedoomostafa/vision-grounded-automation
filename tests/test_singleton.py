import json
import os

import pytest

from src.core.exceptions import SingletonLockError
from src.core.singleton import SingletonLock


def test_singleton_lock_creates_and_releases_lock_file(tmp_path):
    lock_path = tmp_path / ".automation.lock"
    lock = SingletonLock(lock_path)

    lock.acquire()

    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()

    lock.release()

    assert not lock_path.exists()


def test_singleton_lock_blocks_second_instance_for_same_process(tmp_path):
    lock_path = tmp_path / ".automation.lock"
    first = SingletonLock(lock_path)
    second = SingletonLock(lock_path)

    first.acquire()

    with pytest.raises(SingletonLockError, match="already running"):
        second.acquire()

    first.release()


def test_singleton_lock_replaces_stale_lock_file(tmp_path):
    lock_path = tmp_path / ".automation.lock"
    lock_path.write_text(
        json.dumps(
            {
                "pid": 999999,
                "process_create_time": 0.0,
                "command": "stale-process",
            }
        ),
        encoding="utf-8",
    )

    lock = SingletonLock(lock_path)
    lock.acquire()

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()

    lock.release()

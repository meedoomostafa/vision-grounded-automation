from concurrent.futures import ThreadPoolExecutor

import pytest

from src.core.key_manager import RoundRobinKeyManager


def test_round_robin_rotates_in_order():
    manager = RoundRobinKeyManager(["key-a", "key-b", "key-c"])

    assert manager.next_key() == "key-a"
    assert manager.next_key() == "key-b"
    assert manager.next_key() == "key-c"
    assert manager.next_key() == "key-a"


def test_round_robin_deduplicates_and_splits_compound_values():
    manager = RoundRobinKeyManager([" key-a \nkey-b ", "key-b", "key-c,key-a"])

    assert manager.keys == ("key-a", "key-b", "key-c")


def test_round_robin_from_env_prefers_index_order_then_fallbacks():
    env = {
        "AI__Gemini__ApiKeys__2": "key-c",
        "AI__Gemini__ApiKeys__0": "key-a",
        "AI__Gemini__ApiKeys__1": "key-b",
        "GOOGLE_API_KEY": "legacy-key",
    }

    manager = RoundRobinKeyManager.from_env(env)

    assert manager.keys == ("key-a", "key-b", "key-c", "legacy-key")


def test_round_robin_from_env_is_case_insensitive():
    env = {
        "AI__GEMINI__APIKEYS__1": "key-b",
        "AI__GEMINI__APIKEYS__0": "key-a",
        "google_api_key": "legacy-key",
    }

    manager = RoundRobinKeyManager.from_env(env)

    assert manager.keys == ("key-a", "key-b", "legacy-key")


def test_round_robin_empty_manager_raises():
    manager = RoundRobinKeyManager([])

    with pytest.raises(RuntimeError, match="No Gemini API keys configured"):
        manager.next_key()


def test_round_robin_is_thread_safe():
    manager = RoundRobinKeyManager(["key-a", "key-b"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: manager.next_key(), range(8)))

    assert results.count("key-a") == 4
    assert results.count("key-b") == 4

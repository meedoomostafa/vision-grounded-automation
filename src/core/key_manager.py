from __future__ import annotations

from collections.abc import Iterable, Mapping
from threading import Lock


def _split_compound_value(value: str) -> list[str]:
    parts: list[str] = []
    normalized = value.replace("\r", "\n").replace(",", "\n").replace(";", "\n")
    for raw_part in normalized.split("\n"):
        part = raw_part.strip()
        if part:
            parts.append(part)
    return parts


def _normalize_keys(keys: Iterable[str | None]) -> tuple[str, ...]:
    unique_keys: list[str] = []
    seen: set[str] = set()

    for raw_key in keys:
        if raw_key is None:
            continue

        for key in _split_compound_value(raw_key):
            if key in seen:
                continue
            unique_keys.append(key)
            seen.add(key)

    return tuple(unique_keys)


class RoundRobinKeyManager:
    """Thread-safe round-robin key rotation for Gemini API credentials."""

    def __init__(self, keys: Iterable[str]):
        self._keys = _normalize_keys(keys)
        self._index = 0
        self._lock = Lock()

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        indexed_prefix: str = "AI__Gemini__ApiKeys__",
        list_name: str = "AI__Gemini__ApiKeys",
        legacy_names: tuple[str, ...] = ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    ) -> "RoundRobinKeyManager":
        ordered_keys: list[str | None] = []
        indexed_values: list[tuple[int, str]] = []
        indexed_prefix_upper = indexed_prefix.upper()
        list_name_upper = list_name.upper()
        legacy_names_upper = {name.upper() for name in legacy_names}

        for name, value in env.items():
            normalized_name = name.upper()
            if not normalized_name.startswith(indexed_prefix_upper):
                continue

            suffix = normalized_name.removeprefix(indexed_prefix_upper)
            if suffix.isdigit():
                indexed_values.append((int(suffix), value))

        for _, value in sorted(indexed_values, key=lambda item: item[0]):
            ordered_keys.append(value)

        for name, value in env.items():
            normalized_name = name.upper()
            if normalized_name == list_name_upper:
                ordered_keys.append(value)
            elif normalized_name in legacy_names_upper:
                ordered_keys.append(value)

        return cls(ordered_keys)

    @property
    def keys(self) -> tuple[str, ...]:
        return self._keys

    def __len__(self) -> int:
        return len(self._keys)

    def __bool__(self) -> bool:
        return bool(self._keys)

    def peek(self) -> str:
        if not self._keys:
            raise RuntimeError("No Gemini API keys configured")
        return self._keys[0]

    def next_key(self) -> str:
        if not self._keys:
            raise RuntimeError("No Gemini API keys configured")

        with self._lock:
            key = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            return key

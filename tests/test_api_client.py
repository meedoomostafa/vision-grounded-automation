from unittest.mock import MagicMock, patch

import requests

from src.automation.api_client import fetch_posts


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=mock
        )
    return mock


@patch("src.automation.api_client._fetch_raw")
def test_fetch_posts_returns_valid_posts(mock_fetch):
    mock_fetch.return_value = [
        {"id": 1, "title": "Test", "body": "Body", "userId": 1},
        {"id": 2, "title": "Test 2", "body": "Body 2", "userId": 1},
    ]
    posts = fetch_posts(limit=10)
    assert len(posts) == 2
    assert posts[0]["id"] == 1
    assert posts[1]["title"] == "Test 2"


@patch("src.automation.api_client._fetch_raw")
def test_fetch_posts_respects_limit(mock_fetch):
    mock_fetch.return_value = [
        {"id": i, "title": f"T{i}", "body": f"B{i}"} for i in range(20)
    ]
    posts = fetch_posts(limit=5)
    assert len(posts) == 5


@patch("src.automation.api_client._fetch_raw")
def test_fetch_posts_skips_invalid_entries(mock_fetch):
    mock_fetch.return_value = [
        {"id": 1, "title": "Good", "body": "ok"},
        {"id": 2, "title": "Missing body"},  # missing "body"
        "not_a_dict",
        {"id": 3, "title": "Also good", "body": "yes"},
    ]
    posts = fetch_posts(limit=10)
    assert len(posts) == 2
    assert posts[0]["id"] == 1
    assert posts[1]["id"] == 3


@patch("src.automation.api_client._fetch_raw")
def test_fetch_posts_returns_empty_on_api_error(mock_fetch):
    from src.core.exceptions import APIError
    mock_fetch.side_effect = APIError("connection refused")
    posts = fetch_posts()
    assert posts == []


@patch("src.automation.api_client._fetch_raw")
def test_fetch_posts_returns_empty_on_non_list_response(mock_fetch):
    mock_fetch.return_value = {"error": "unexpected format"}
    posts = fetch_posts()
    assert posts == []

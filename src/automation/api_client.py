import requests

from src import config
from src.core.exceptions import APIError
from src.core.logger import get_logger
from src.core.retry import retry

logger = get_logger(__name__)

_REQUIRED_FIELDS = {"id", "title", "body"}


@retry(max_attempts=config.MAX_RETRIES, backoff_base=config.BACKOFF_BASE, exceptions=(APIError,))
def _fetch_raw(url: str) -> list[dict]:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise APIError(f"API request failed: {exc}") from exc
    except ValueError as exc:
        raise APIError(f"Invalid JSON response: {exc}") from exc


def fetch_posts(limit: int = config.API_POSTS_LIMIT) -> list[dict]:
    url = f"{config.API_BASE_URL}/posts"
    logger.info("Fetching posts from %s (limit=%d)", url, limit)

    try:
        data = _fetch_raw(url)
    except APIError as exc:
        logger.error("Failed to fetch posts after retries: %s", exc)
        return []

    if not isinstance(data, list):
        logger.error("Expected list from API, got %s", type(data).__name__)
        return []

                        
    valid_posts = []
    for post in data[:limit]:
        if not isinstance(post, dict):
            continue
        if not _REQUIRED_FIELDS.issubset(post.keys()):
            logger.warning("Skipping post with missing fields: %s", post.get("id", "?"))
            continue
        valid_posts.append(post)

    logger.info("Fetched %d valid posts", len(valid_posts))
    return valid_posts

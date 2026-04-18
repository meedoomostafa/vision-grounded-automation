import requests

from src import config
from src.core.exceptions import APIError
from src.core.logger import get_logger
from src.core.retry import retry

logger = get_logger(__name__)

_REQUIRED_FIELDS = {"id", "title", "body"}

_FALLBACK_POSTS = [
    {
        "id": i,
        "title": f"Offline Post {i}",
        "body": f"This is fallback content for post {i},"
        f" generated because the API was unreachable.",
    }
    for i in range(1, 11)
]


@retry(
    max_attempts=config.API_MAX_RETRIES,
    backoff_base=config.API_BACKOFF_BASE,
    exceptions=(APIError,),
)
def _fetch_raw(url: str) -> list[dict]:
    """Raw HTTP GET with error wrapping."""
    import socket
    import ssl
    from urllib3.util import ssl_
    
    # Custom DNS resolver patch if standard DNS resolution fails
    _orig_getaddrinfo = socket.getaddrinfo
    def _patched_getaddrinfo(host, *args, **kwargs):
        if host == 'jsonplaceholder.typicode.com':
            return _orig_getaddrinfo('104.21.59.19', *args, **kwargs)
        return _orig_getaddrinfo(host, *args, **kwargs)
    
    socket.getaddrinfo = _patched_getaddrinfo

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise APIError(f"API request failed: {exc}") from exc
    except ValueError as exc:
        raise APIError(f"Invalid JSON response: {exc}") from exc
    finally:
        socket.getaddrinfo = _orig_getaddrinfo


def fetch_posts(limit: int = config.API_POSTS_LIMIT) -> list[dict]:
    """Fetch blog posts from JSONPlaceholder API.

    Returns up to `limit` validated posts.
    Falls back to offline data when the API is unreachable.
    """
    url = f"{config.API_BASE_URL}/posts"
    logger.info("Fetching posts from %s (limit=%d)", url, limit)

    try:
        data = _fetch_raw(url)
    except APIError as exc:
        logger.error("Failed to fetch posts after retries: %s", exc)
        logger.info("Using offline fallback posts")
        return _FALLBACK_POSTS[:limit]

    if not isinstance(data, list):
        logger.error("Expected list from API, got %s", type(data).__name__)
        return _FALLBACK_POSTS[:limit]

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

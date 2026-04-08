import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, status

# Global in-memory store: {api_key_id: [timestamps]}
_request_log: Dict[int, List[float]] = defaultdict(list)


def check_rate_limit(api_key_id: int, limit: int = 60, window: int = 60) -> None:
    """
    Sliding-window rate limiter.
    Raises HTTP 429 if the caller has exceeded `limit` requests in the last
    `window` seconds.
    """
    now = time.monotonic()
    cutoff = now - window
    timestamps = _request_log[api_key_id]

    # Prune old entries
    _request_log[api_key_id] = [t for t in timestamps if t > cutoff]

    if len(_request_log[api_key_id]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit} requests per {window}s",
            headers={"Retry-After": str(window)},
        )

    _request_log[api_key_id].append(now)


def get_current_count(api_key_id: int, window: int = 60) -> int:
    now = time.monotonic()
    cutoff = now - window
    return len([t for t in _request_log.get(api_key_id, []) if t > cutoff])

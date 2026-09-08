"""Fan-out for server-sent events.

Every browser watching the leaderboard holds one queue. Publishing drops a
payload into all of them; a subscriber that has stopped draining (a closed
laptop lid) gets its oldest events discarded rather than being allowed to grow
without bound.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

_subscribers: set[asyncio.Queue] = set()
MAX_PENDING = 16


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_PENDING)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)


def publish(event: str, data: Any) -> None:
    """Non-blocking broadcast. Safe to call from the event loop thread."""
    payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for queue in list(_subscribers):
        while True:
            try:
                queue.put_nowait(payload)
                break
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break


def publish_threadsafe(loop: asyncio.AbstractEventLoop, event: str, data: Any) -> None:
    """Broadcast from a worker thread (the showdown runs off-loop)."""
    try:
        loop.call_soon_threadsafe(publish, event, data)
    except RuntimeError:
        pass


def subscriber_count() -> int:
    return len(_subscribers)

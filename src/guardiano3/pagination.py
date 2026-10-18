"""Cursor pagination, as an iterator.

The API returns an opaque `nextCursor`; a caller should never have to loop on it
by hand, and should never construct one. `iterate` turns the pages back into a
single sequence.

Lazy on purpose: it fetches a page only when the caller has consumed the
previous one, so `next(iterate(...))` costs one request rather than walking the
whole history.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Optional


def iterate(
    fetch_page: Callable[..., Any],
    *,
    limit: Optional[int] = None,
    max_items: Optional[int] = None,
    **kwargs: Any,
) -> Iterator[Any]:
    """Yield every item across pages.

    `fetch_page` takes `cursor` and `limit` keyword arguments and returns an
    object with `items`, `next_cursor` and `has_more`.
    """
    cursor: Optional[str] = None
    produced = 0

    while True:
        page = fetch_page(cursor=cursor, limit=limit, **kwargs)
        for item in getattr(page, "items", None) or []:
            yield item
            produced += 1
            if max_items is not None and produced >= max_items:
                return

        cursor = getattr(page, "next_cursor", None)
        # `has_more` alone is not enough: a page can report more while giving no
        # cursor to reach it, and looping on that would spin forever.
        if not cursor:
            return

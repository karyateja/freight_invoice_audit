"""Small shared helpers."""
from __future__ import annotations

import math
from decimal import Decimal

from . import ids


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def dec(x: float, places: str) -> Decimal:
    """Float -> Decimal at a fixed precision (via the shortest float repr, then half-up)."""
    from decimal import ROUND_HALF_UP
    return Decimal(repr(x)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def event_rows(prefix: str, parent_col: str, events: dict) -> list[dict]:
    """events: {entity_id: [(from, to, ts, actor, note), ...]} -> append-only event rows."""
    rows = []
    for entity in sorted(events):
        for seq, (frm, to, ts, actor, note) in enumerate(events[entity], 1):
            rows.append({"event_id": ids.event_id(prefix, entity, seq), parent_col: entity, "event_seq": seq,
                         "from_status": frm, "to_status": to, "event_at": ts, "actor_role": actor,
                         "note": note or None})
    return rows

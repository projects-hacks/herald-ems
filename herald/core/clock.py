"""Spoken clock times ("1:40", "0630", "10 pm") resolved to the most recent past local time."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from .schema import utcnow


def parse_clock(text: str, tz: ZoneInfo, now: Optional[datetime] = None) -> Optional[datetime]:
    now = (now or utcnow()).astimezone(tz)
    s = str(text).strip().lower().replace(".", "")
    ampm = None
    for tag in ("am", "pm"):
        if s.endswith(tag):
            ampm, s = tag, s[: -len(tag)].strip()
    if ":" in s:
        hh, mm = s.split(":", 1)
    elif s.isdigit() and len(s) in (3, 4):
        hh, mm = s[:-2], s[-2:]
    elif s.isdigit():
        hh, mm = s, "0"
    else:
        return None
    try:
        h, m = int(hh), int(mm)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    hours = [h]
    if ampm == "pm" and h < 12:
        hours = [h + 12]
    elif ampm == "am" and h == 12:
        hours = [0]
    elif ampm is None and h <= 12:
        hours = [h % 12, h % 12 + 12]
    candidates = [c for hr in hours for day in (0, -1)
                  if (c := (now + timedelta(days=day)).replace(hour=hr, minute=m, second=0, microsecond=0))
                  <= now + timedelta(minutes=1)]
    return max(candidates) if candidates else None

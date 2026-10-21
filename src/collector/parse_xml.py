"""Parse DB Timetables XML responses into tidy tables (one row per stop event).

Structure of the responses (verified against real responses in tests/fixtures):

    <timetable station="Frankfurt(Main)Hbf">
      <s id="<trip>-<YYMMddHHmm>-<stop no>" [eva="8000105"]>   one train stop
        <tl c="ICE" n="697" f="F" t="p" o="80"/>             train label (category, number,
                                                              filter flag, trip type, owner)
        <ar pt="2609082345" pp="9" l="RE30" ppth="A|B|C"/>   arrival  (planned time/platform/path)
        <dp ct="2609090123" cp="19" cs="c" clt="..."/>       departure (changed time/platform,
                                                              change status, cancellation time)
      </s>
    </timetable>

All times are `YYMMddHHmm` in Europe/Berlin local time without an offset; they are
returned as naive datetimes here and localised in the transform step.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from lxml import etree

EVENT_TAGS = {"ar": "arrival", "dp": "departure"}
CHANGE_STATUS = {"c": "cancelled", "a": "added", "p": "planned"}

PLAN_COLUMNS = [
    "stop_id", "eva", "station_name", "event", "train_category", "train_number",
    "filter_flag", "trip_type", "operator", "line", "planned_time", "planned_platform",
    "origin", "destination",
]
CHANGE_COLUMNS = [
    "stop_id", "eva", "event", "changed_time", "changed_platform", "change_status",
    "is_cancelled", "cancellation_time", "planned_time", "line", "train_category",
    "train_number", "filter_flag", "is_hidden",
]


def parse_ts(value: str | None) -> datetime | None:
    """Convert the API's `YYMMddHHmm` format to a naive local datetime (None if absent)."""
    if not value:
        return None
    return datetime.strptime(value, "%y%m%d%H%M")


def _root(xml: str | bytes) -> etree._Element:
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    # resolve_entities/no_network: never fetch anything referenced by the document.
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.fromstring(data, parser=parser)


def _path_ends(event_tag: str, path: str | None) -> tuple[str | None, str | None]:
    """Return (origin, destination) from a `ppth` path.

    For an arrival the path lists the stations *before* this stop, so its first entry
    is the origin; for a departure it lists the stations *after*, so its last entry
    is the destination.
    """
    if not path:
        return None, None
    stations = path.split("|")
    return (stations[0], None) if event_tag == "ar" else (None, stations[-1])


def parse_station(xml: str | bytes) -> list[dict]:
    """Parse a `/station` response into dicts with name, eva, ds100 and related EVAs (`meta`)."""
    stations = []
    for st in _root(xml).iter("station"):
        meta = st.get("meta")
        stations.append(
            {
                "name": st.get("name"),
                "eva": st.get("eva"),
                "ds100": st.get("ds100"),
                "meta_evas": meta.split("|") if meta else [],
            }
        )
    return stations


def parse_plan(xml: str | bytes, eva: str) -> pd.DataFrame:
    """Parse a `/plan` response into one row per planned arrival/departure."""
    root = _root(xml)
    station_name = root.get("station")
    rows = []
    for s in root.iter("s"):
        tl = s.find("tl")
        for tag, event in EVENT_TAGS.items():
            ev = s.find(tag)
            if ev is None:
                continue
            origin, destination = _path_ends(tag, ev.get("ppth"))
            rows.append(
                {
                    "stop_id": s.get("id"),
                    "eva": s.get("eva") or eva,
                    "station_name": station_name,
                    "event": event,
                    "train_category": tl.get("c") if tl is not None else None,
                    "train_number": tl.get("n") if tl is not None else None,
                    "filter_flag": tl.get("f") if tl is not None else None,
                    "trip_type": tl.get("t") if tl is not None else None,
                    "operator": tl.get("o") if tl is not None else None,
                    "line": ev.get("l"),
                    "planned_time": parse_ts(ev.get("pt")),
                    "planned_platform": ev.get("pp"),
                    "origin": origin,
                    "destination": destination,
                }
            )
    return pd.DataFrame(rows, columns=PLAN_COLUMNS)


def parse_changes(xml: str | bytes, eva: str) -> pd.DataFrame:
    """Parse a `/fchg` or `/rchg` response into one row per changed arrival/departure.

    Most stops carry only changed values (`ct`, `cp`, `cs`); unplanned trains also carry
    their own `<tl>` and planned values, which are kept so they are not lost in the join.
    """
    rows = []
    for s in _root(xml).iter("s"):
        tl = s.find("tl")
        for tag, event in EVENT_TAGS.items():
            ev = s.find(tag)
            if ev is None:
                continue
            status = ev.get("cs")
            rows.append(
                {
                    "stop_id": s.get("id"),
                    "eva": s.get("eva") or eva,
                    "event": event,
                    "changed_time": parse_ts(ev.get("ct")),
                    "changed_platform": ev.get("cp"),
                    "change_status": CHANGE_STATUS.get(status, status),
                    "is_cancelled": status == "c",
                    "cancellation_time": parse_ts(ev.get("clt")),
                    "planned_time": parse_ts(ev.get("pt")),
                    "line": ev.get("l"),
                    "train_category": tl.get("c") if tl is not None else None,
                    "train_number": tl.get("n") if tl is not None else None,
                    "filter_flag": tl.get("f") if tl is not None else None,
                    "is_hidden": ev.get("hi") == "1",
                }
            )
    return pd.DataFrame(rows, columns=CHANGE_COLUMNS)

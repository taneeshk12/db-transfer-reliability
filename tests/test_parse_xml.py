"""Tests for the Timetables XML parser, based on real responses (see tests/fixtures/README.md)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from lxml import etree

from src.collector.parse_xml import (
    CHANGE_COLUMNS,
    PLAN_COLUMNS,
    parse_changes,
    parse_plan,
    parse_station,
    parse_ts,
)

FIXTURES = Path(__file__).parent / "fixtures"
EVA = "8000105"


@pytest.fixture(scope="module")
def plan_xml() -> str:
    return (FIXTURES / "plan_8000105_2609082300.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fchg_xml() -> str:
    return (FIXTURES / "fchg_8000105_subset.xml").read_text(encoding="utf-8")


# --- timestamps ------------------------------------------------------------------------
def test_parse_ts_converts_api_format_to_naive_local_datetime() -> None:
    assert parse_ts("2609082345") == datetime(2026, 9, 8, 23, 45)
    assert parse_ts(None) is None
    assert parse_ts("") is None


def test_parse_ts_rejects_malformed_values() -> None:
    with pytest.raises(ValueError):
        parse_ts("26-09-08 23:45")


# --- plan --------------------------------------------------------------------------------
def test_plan_has_one_row_per_arrival_and_departure(plan_xml: str) -> None:
    df = parse_plan(plan_xml, EVA)
    expected = len(etree.fromstring(plan_xml.encode()).xpath("//s/ar | //s/dp"))
    assert len(df) == expected == 27
    assert list(df.columns) == PLAN_COLUMNS
    assert df["eva"].eq(EVA).all()
    assert df["station_name"].eq("Frankfurt(Main)Hbf").all()


def test_plan_departure_fields(plan_xml: str) -> None:
    df = parse_plan(plan_xml, EVA)
    row = df[(df["train_category"] == "RE") & (df["train_number"] == "4168")].iloc[0]
    assert row["event"] == "departure"
    assert row["planned_time"] == datetime(2026, 9, 8, 23, 20)
    assert row["planned_platform"] == "15"
    assert row["line"] == "RE30"
    assert row["filter_flag"] == "N"
    assert row["destination"] == "Treysa"  # last station of the departure path
    assert row["origin"] is None


def test_plan_arrival_origin_is_first_path_station(plan_xml: str) -> None:
    df = parse_plan(plan_xml, EVA)
    row = df[(df["train_category"] == "ICE") & (df["train_number"] == "697")].iloc[0]
    assert row["event"] == "arrival"
    assert row["origin"] == "Berlin Gesundbrunnen"
    assert row["filter_flag"] == "F"
    assert row["line"] is None  # long-distance trains carry no line


def test_plan_empty_timetable_returns_typed_empty_frame() -> None:
    df = parse_plan("<timetable station='X'/>", EVA)
    assert df.empty
    assert list(df.columns) == PLAN_COLUMNS


# --- changes -------------------------------------------------------------------------------
def test_changes_row_count_and_columns(fchg_xml: str) -> None:
    df = parse_changes(fchg_xml, EVA)
    expected = len(etree.fromstring(fchg_xml.encode()).xpath("//s/ar | //s/dp"))
    assert len(df) == expected
    assert list(df.columns) == CHANGE_COLUMNS


def test_cancelled_events_have_cancellation_time_but_no_changed_time(fchg_xml: str) -> None:
    df = parse_changes(fchg_xml, EVA)
    cancelled = df[df["is_cancelled"]]
    assert len(cancelled) == 6
    assert cancelled["change_status"].eq("cancelled").all()
    assert cancelled["cancellation_time"].notna().all()
    assert cancelled["changed_time"].isna().all()


def test_every_planned_stop_joins_to_a_change(plan_xml: str, fchg_xml: str) -> None:
    plan = parse_plan(plan_xml, EVA)
    changes = parse_changes(fchg_xml, EVA)
    merged = plan.merge(changes, on=["stop_id", "eva", "event"], how="left", indicator=True)
    assert merged["_merge"].eq("both").all()


def test_delay_past_midnight(plan_xml: str, fchg_xml: str) -> None:
    """ICE 697 is planned at 23:45 and arrives 00:13 the next day: delay must be +28, not -1412."""
    plan = parse_plan(plan_xml, EVA)
    changes = parse_changes(fchg_xml, EVA)
    m = plan.merge(changes, on=["stop_id", "eva", "event"], suffixes=("", "_chg"))
    row = m[(m["train_category"] == "ICE") & (m["train_number"] == "697")].iloc[0]
    assert row["changed_time"] == datetime(2026, 9, 9, 0, 13)
    assert (row["changed_time"] - row["planned_time"]).total_seconds() / 60 == 28


def test_cancelled_planned_train(plan_xml: str, fchg_xml: str) -> None:
    plan = parse_plan(plan_xml, EVA)
    changes = parse_changes(fchg_xml, EVA)
    m = plan.merge(changes, on=["stop_id", "eva", "event"], suffixes=("", "_chg"))
    row = m[(m["train_category"] == "IC") & (m["train_number"] == "2442")].iloc[0]
    assert bool(row["is_cancelled"]) is True


# --- station ---------------------------------------------------------------------------------
def test_parse_station_from_real_response() -> None:
    """Uses a /station response saved from the first live collector run."""
    path = FIXTURES / "station_frankfurt.xml"
    if not path.exists():
        pytest.skip("No real /station fixture yet (added after the first live run)")
    stations = parse_station(path.read_text(encoding="utf-8"))
    frankfurt = [s for s in stations if s["name"] == "Frankfurt(Main)Hbf"]
    assert len(frankfurt) == 1
    assert frankfurt[0]["eva"] == "8000105"

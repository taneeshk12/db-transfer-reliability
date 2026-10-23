"""Tests for the transform: dedup, delays, on-time flags and train classification (synthetic rows)."""

from __future__ import annotations

from datetime import date, datetime

import duckdb
import pandas as pd
import pytest

from src.transform import build_dim_date, build_stops, classify_sql, hub_holidays

T = datetime(2026, 5, 4, 8, 0)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "a", "hub": "Köln Hbf", "eva": "08000207", "xml_station_name": "Köln Hbf",
        "train_type": "ICE", "train_number": "1", "line_number": None, "train_line_ride_id": "r1",
        "arrival_planned_time": T, "arrival_change_time": T,
        "departure_planned_time": T, "departure_change_time": T,
        "arrival_is_canceled": False, "departure_is_canceled": False,
        "has_plan_record": True, "is_replacement_train": False, "file_month": "2026-05",
    }
    row.update(overrides)
    return row


def _stops(rows: list[dict[str, object]]) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("src", pd.DataFrame(rows))
    build_stops(con, "src")
    return con.execute("SELECT * FROM stops ORDER BY id").df()


def test_dedup_keeps_plan_record_row_across_eva_numbers() -> None:
    stops = _stops([
        _row(id="a", eva="08000207", has_plan_record=False),
        _row(id="b", eva="08098207", has_plan_record=True),
        _row(id="c", train_line_ride_id="r2"),
    ])
    assert list(stops["id"]) == ["b", "c"]


def test_rows_without_planned_time_are_dropped() -> None:
    stops = _stops([_row(arrival_planned_time=None, departure_planned_time=None), _row(id="b")])
    assert list(stops["id"]) == ["b"]


@pytest.mark.parametrize(
    ("delay", "on_time"),
    [(-2, True), (0, True), (5, True), (6, False), (30, False)],
)
def test_on_time_threshold_is_strictly_below_six_minutes(delay: int, on_time: bool) -> None:
    actual = T + pd.Timedelta(minutes=delay)
    stops = _stops([_row(arrival_change_time=actual, departure_change_time=actual)])
    assert stops.loc[0, "departure_delay_min"] == delay
    assert stops.loc[0, "is_departure_on_time"] == on_time
    assert stops.loc[0, "is_arrival_on_time"] == on_time


def test_cancelled_side_has_no_delay_and_no_on_time_flag() -> None:
    stops = _stops([_row(departure_is_canceled=True)])
    assert pd.isna(stops.loc[0, "departure_delay_min"])
    assert pd.isna(stops.loc[0, "is_departure_on_time"])
    assert stops.loc[0, "arrival_delay_min"] == 0


def test_implausible_delay_is_flagged_and_excluded_from_on_time() -> None:
    late = T + pd.Timedelta(minutes=700)
    stops = _stops([_row(departure_change_time=late)])
    assert bool(stops.loc[0, "is_delay_implausible"])
    assert pd.isna(stops.loc[0, "is_departure_on_time"])


@pytest.mark.parametrize(
    ("train_type", "line_number", "product", "category"),
    [
        ("ICE", None, "ICE", "long_distance"),
        ("FLX30", None, "FLX", "long_distance"),
        ("S", "S3", "S", "s_bahn"),
        ("SBH", "S5", "S", "s_bahn"),
        ("ME", "RB31", "RB", "regional"),
        ("vlx", "RE3", "RE", "regional"),
        ("RE", "FEX", "RE", "regional"),
        ("RSM", "HBX", "RE", "regional"),
        ("Bus", "S4", "BUS", "bus"),
        ("D", "SEV", "BUS", "bus"),
        ("GV", None, None, "other"),
    ],
)
def test_train_classification(train_type: str, line_number: str | None, product: str | None, category: str) -> None:
    product_sql, category_sql = classify_sql("t", "l")
    got = duckdb.execute(
        f"SELECT {product_sql}, {category_sql} FROM (SELECT ?::VARCHAR AS t, ?::VARCHAR AS l)",
        [train_type, line_number],
    ).fetchone()
    assert got == (product, category)


def test_dim_date_marks_weekends_and_national_holidays() -> None:
    dim = build_dim_date(date(2026, 4, 30), date(2026, 5, 3)).set_index("date")
    assert len(dim) == 4
    assert dim.loc[date(2026, 5, 1), "is_national_holiday"]
    assert not dim.loc[date(2026, 4, 30), "is_national_holiday"]
    assert dim.loc[date(2026, 5, 2), "is_weekend"] and dim.loc[date(2026, 5, 3), "weekday_num"] == 7


def test_state_holidays_differ_between_hubs() -> None:
    # Corpus Christi (4 Jun 2026) is a holiday in Bavaria and NRW, not in Berlin or Hamburg.
    hol = hub_holidays(date(2026, 6, 4), date(2026, 6, 4))
    assert set(hol["hub"]) >= {"München Hbf", "Köln Hbf"}
    assert not {"Berlin Hbf", "Hamburg Hbf"} & set(hol["hub"])

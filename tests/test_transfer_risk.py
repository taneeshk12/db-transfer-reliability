"""Tests for the transfer-risk pairing (synthetic star-schema rows)."""

from __future__ import annotations

from datetime import datetime, timedelta

import duckdb
import pandas as pd

from src.transfer_risk import AGG_TABLE, build_transfer_risk

T = datetime(2026, 5, 4, 8, 0)  # a Monday


def _stop(key: int, ride: str, arr: datetime | None, arr_delay: int | None,
          dep: datetime | None, dep_delay: int | None, **flags: bool) -> dict[str, object]:
    return {
        "stop_key": key, "date_key": 20260504, "station_key": 1, "train_key": 1, "ride_id": ride,
        "arrival_planned": arr,
        "arrival_actual": arr + timedelta(minutes=arr_delay) if arr is not None else None,
        "arrival_delay_min": arr_delay,
        "departure_planned": dep,
        "departure_actual": dep + timedelta(minutes=dep_delay) if dep is not None else None,
        "is_arrival_cancelled": flags.get("arr_cancelled", False),
        "is_departure_cancelled": flags.get("dep_cancelled", False),
        "is_delay_implausible": False,
    }


def _risk(stops: list[dict[str, object]], buffers: tuple[int, ...] = (5,)) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("fact_stop", pd.DataFrame(stops))
    con.register("dim_station", pd.DataFrame({"station_key": [1], "hub": ["Köln Hbf"]}))
    con.register("dim_train", pd.DataFrame({"train_key": [1], "train_category": ["regional"]}))
    con.register("dim_date", pd.DataFrame({"date_key": [20260504], "is_weekend": [False]}))
    build_transfer_risk(con, buffers)
    return con.execute(f"SELECT * FROM {AGG_TABLE}").df()


def test_late_arrival_misses_on_time_connection() -> None:
    risk = _risk([_stop(1, "in", T, 6, None, None), _stop(2, "out", None, None, T + timedelta(minutes=5), 0)])
    assert risk.loc[0, ["n_pairs", "n_missed", "n_missed_if_departure_on_time"]].tolist() == [1, 1, 1]


def test_late_connection_rescues_the_transfer() -> None:
    # Arrival 6 min late, connection 3 min late: actual gap 2 min -> caught; naive rule says missed.
    risk = _risk([_stop(1, "in", T, 6, None, None), _stop(2, "out", None, None, T + timedelta(minutes=5), 3)])
    assert risk.loc[0, ["n_missed", "n_missed_if_departure_on_time"]].tolist() == [0, 1]


def test_arriving_exactly_at_departure_counts_as_missed() -> None:
    risk = _risk([_stop(1, "in", T, 5, None, None), _stop(2, "out", None, None, T + timedelta(minutes=5), 0)])
    assert risk.loc[0, "n_missed"] == 1


def test_only_exact_buffer_same_train_and_cancellations_are_excluded() -> None:
    risk = _risk([
        _stop(1, "in", T, 0, T + timedelta(minutes=5), 0),               # same run: through train
        _stop(2, "other", None, None, T + timedelta(minutes=6), 0),      # 6 min, not 5
        _stop(3, "cxl", None, None, T + timedelta(minutes=5), 0, dep_cancelled=True),
        _stop(4, "ok", None, None, T + timedelta(minutes=5), 0),
    ])
    assert risk["n_pairs"].sum() == 1


def test_each_buffer_is_evaluated_separately() -> None:
    risk = _risk(
        [_stop(1, "in", T, 7, None, None),
         _stop(2, "a", None, None, T + timedelta(minutes=5), 0),
         _stop(3, "b", None, None, T + timedelta(minutes=10), 0)],
        buffers=(5, 10),
    ).set_index("buffer_min")
    assert risk.loc[5, "n_missed"] == 1 and risk.loc[10, "n_missed"] == 0

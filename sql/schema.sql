-- Star schema for train stops at the six focus hubs (PostgreSQL 16).
-- Grain of fact_stop: one train stop at one hub (deduplicated across the hub's EVA numbers).
-- All timestamps are naive Europe/Berlin local time, as delivered by the source.
-- Idempotent: safe to run on every load; load.py truncates and reloads the tables.

CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key            integer PRIMARY KEY,          -- YYYYMMDD
    date                date NOT NULL UNIQUE,
    year                smallint NOT NULL,
    month               smallint NOT NULL,
    month_name          text NOT NULL,
    iso_week            smallint NOT NULL,
    weekday_num         smallint NOT NULL,             -- 1 = Monday … 7 = Sunday
    weekday_name        text NOT NULL,
    is_weekend          boolean NOT NULL,
    is_national_holiday boolean NOT NULL,
    holiday_name        text                           -- national holiday name, NULL otherwise
);

CREATE TABLE IF NOT EXISTS dw.dim_station (
    station_key   smallint PRIMARY KEY,
    eva           char(8) NOT NULL UNIQUE,
    hub           text NOT NULL,
    platform_area text NOT NULL,                       -- xml_station_name, e.g. "Hamburg Hbf (S-Bahn)"
    state_code    char(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_train (
    train_key      integer PRIMARY KEY,
    train_category text NOT NULL
        CHECK (train_category IN ('long_distance', 'regional', 's_bahn', 'bus', 'other')),
    product        text,                               -- ICE, IC, RE, RB, S, … (NULL for "other")
    train_type     text NOT NULL,                      -- raw source code (product or operator)
    line_number    text,                               -- NULL for most long-distance trains
    line_label     text NOT NULL,                      -- line_number, else product, else train_type
    UNIQUE NULLS NOT DISTINCT (train_type, line_number)
);

CREATE TABLE IF NOT EXISTS dw.fact_stop (
    stop_key               bigint PRIMARY KEY,
    source_id              text NOT NULL UNIQUE,       -- `id` of the kept source row (lineage)
    date_key               integer NOT NULL REFERENCES dw.dim_date,
    planned_hour           smallint NOT NULL CHECK (planned_hour BETWEEN 0 AND 23),
    station_key            smallint NOT NULL REFERENCES dw.dim_station,
    train_key              integer NOT NULL REFERENCES dw.dim_train,
    train_number           text NOT NULL,
    ride_id                text NOT NULL,
    arrival_planned        timestamp,
    arrival_actual         timestamp,
    departure_planned      timestamp,
    departure_actual       timestamp,
    arrival_delay_min      integer,                    -- NULL if no arrival or cancelled
    departure_delay_min    integer,                    -- NULL if no departure or cancelled
    is_arrival_cancelled   boolean NOT NULL,
    is_departure_cancelled boolean NOT NULL,
    is_cancelled           boolean NOT NULL,           -- either side cancelled
    is_arrival_on_time     boolean,                    -- delay < 6 min; NULL if not measurable
    is_departure_on_time   boolean,
    is_delay_implausible   boolean NOT NULL,           -- a delay above MAX_PLAUSIBLE_DELAY_MIN
    is_hub_holiday         boolean NOT NULL,           -- public holiday in the hub's state
    has_plan_record        boolean NOT NULL,
    is_replacement_train   boolean NOT NULL,
    file_month             char(7) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_fact_stop_date ON dw.fact_stop (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_stop_station ON dw.fact_stop (station_key);
CREATE INDEX IF NOT EXISTS ix_fact_stop_train ON dw.fact_stop (train_key);

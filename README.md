"""
VoltRelay data loader
---------------------
Reads cleaned Parquet data with DuckDB.

Important:
- Does NOT load all swap-event rows into pandas.
- Aggregations are performed inside DuckDB.
- Returns small pandas DataFrames for charts and tables.
- Uses the existing cleaned project data; no synthetic data.
"""

from pathlib import Path
from functools import lru_cache

import duckdb
import pandas as pd
import streamlit as st


# ---------------------------------------------------------
# 1. PROJECT PATHS
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

CLEAN_DIR = ROOT / "data" / "cleaned"
SWAP_DIR = CLEAN_DIR / "swap_events_parts"

STATIONS_PATH = CLEAN_DIR / "stations_clean.parquet"
RIDERS_PATH = CLEAN_DIR / "riders_clean.parquet"
BATTERIES_PATH = CLEAN_DIR / "batteries_clean.parquet"
TELEMETRY_PATH = CLEAN_DIR / "station_hourly_status_clean.parquet"

KPI_DIR = ROOT / "reports" / "kpi"

COMPLETED_LABEL = "swap_completed"


# ---------------------------------------------------------
# 2. DUCKDB CONNECTION AND SOURCE HELPERS
# ---------------------------------------------------------

def get_connection():
    """
    Create a DuckDB connection.

    Each query uses a connection that is closed afterward.
    DuckDB can scan Parquet files directly without reading
    the entire dataset into a pandas DataFrame.
    """
    return duckdb.connect(database=":memory:")


def _sql_path(path: Path) -> str:
    """Format a Windows or other filesystem path for SQL."""
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _swap_source():
    """
    Return the SQL expression for all swap Parquet parts.

    union_by_name handles files whose columns may differ
    between Parquet parts.
    """
    if not SWAP_DIR.exists():
        raise FileNotFoundError(
            f"Swap parts folder not found: {SWAP_DIR}"
        )

    files = sorted(SWAP_DIR.glob("*.parquet"))

    if not files:
        raise FileNotFoundError(
            f"No Parquet files found in {SWAP_DIR}"
        )

    # Use an explicit list of existing files.
    paths = "[" + ", ".join(
        "'" + _sql_path(file) + "'"
        for file in files
    ) + "]"

    return f"read_parquet({paths}, union_by_name=true)"


def _reference_source(path: Path):
    """Return a DuckDB SQL source for a reference Parquet file."""
    if not path.exists():
        return None

    return f"read_parquet('{_sql_path(path)}')"


@st.cache_data(show_spinner=False)
def get_swap_columns():
    """Get swap-event column names without loading the rows."""
    con = get_connection()

    try:
        source = _swap_source()

        result = con.execute(
            f"DESCRIBE SELECT * FROM {source}"
        ).fetchdf()

        return result["column_name"].tolist()

    finally:
        con.close()


def _has_column(column: str) -> bool:
    """Check whether a source column exists."""
    return column in get_swap_columns()


# ---------------------------------------------------------
# 3. SMALL REFERENCE TABLES
# ---------------------------------------------------------

@st.cache_data(show_spinner="Loading reference data...")
def load_reference(path_string: str) -> pd.DataFrame:
    """
    Load a small reference table such as stations or riders.

    This is intentionally for reference tables, not swap events.
    """
    path = Path(path_string)

    if not path.exists():
        return pd.DataFrame()

    con = get_connection()

    try:
        source = _reference_source(path)

        return con.execute(
            f"SELECT * FROM {source}"
        ).fetchdf()

    finally:
        con.close()


def load_stations():
    return load_reference(str(STATIONS_PATH))


def load_riders():
    return load_reference(str(RIDERS_PATH))


def load_batteries():
    return load_reference(str(BATTERIES_PATH))


def load_telemetry():
    return load_reference(str(TELEMETRY_PATH))


# ---------------------------------------------------------
# 4. BASE QUERY WITH STATION METADATA
# ---------------------------------------------------------

@st.cache_data(show_spinner=False)
def _station_columns():
    """Get station reference columns."""
    if not STATIONS_PATH.exists():
        return []

    con = get_connection()

    try:
        source = _reference_source(STATIONS_PATH)

        result = con.execute(
            f"DESCRIBE SELECT * FROM {source}"
        ).fetchdf()

        return result["column_name"].tolist()

    finally:
        con.close()


def _base_query():
    """
    Build a SQL query with event fields and station metadata.

    Station attributes are added only if the actual station
    reference file contains the relevant columns.
    """
    source = _swap_source()
    swap_columns = get_swap_columns()

    select_fields = ["s.*"]

    station_cols = _station_columns()

    if (
        STATIONS_PATH.exists()
        and "station_id" in swap_columns
        and "station_id" in station_cols
    ):
        metadata_cols = [
            "city",
            "zone",
            "location_type",
            "host_type",
        ]

        selected_metadata = [
            col for col in metadata_cols
            if col in station_cols
        ]

        if selected_metadata:
            metadata_sql = ", ".join(
                f"st.{col} AS station_{col}"
                for col in selected_metadata
            )

            select_fields.append(metadata_sql)

            station_source = _reference_source(STATIONS_PATH)

            join_sql = f"""
                LEFT JOIN (
                    SELECT *
                    FROM (
                        SELECT *,
                               ROW_NUMBER() OVER (
                                   PARTITION BY CAST(station_id AS VARCHAR)
                                   ORDER BY station_id
                               ) AS _rn
                        FROM {station_source}
                    )
                    WHERE _rn = 1
                ) st
                ON CAST(s.station_id AS VARCHAR)
                 = CAST(st.station_id AS VARCHAR)
            """
        else:
            join_sql = ""

    else:
        join_sql = ""

    return f"""
        SELECT {", ".join(select_fields)}
        FROM {source} s
        {join_sql}
    """


# ---------------------------------------------------------
# 5. FILTER BUILDING
# ---------------------------------------------------------

def _filter_sql(filters=None, available_columns=None):
    """
    Build parameterized WHERE conditions.

    filters example:
    {
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "city": "Bengaluru",
        "station": "ST001"
    }
    """
    filters = filters or {}
    available_columns = available_columns or get_swap_columns()

    conditions = []
    params = []

    start_date = filters.get("start_date")
    end_date = filters.get("end_date")

    if "event_ts" in available_columns:
        if start_date:
            conditions.append("CAST(event_ts AS DATE) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("CAST(event_ts AS DATE) <= ?")
            params.append(end_date)

    city = filters.get("city", "All cities")

    if city and city != "All cities":
        station_cols = _station_columns()

        if "city" in station_cols:
            conditions.append("station_city = ?")
            params.append(str(city))

        elif "city" in available_columns:
            conditions.append("CAST(city AS VARCHAR) = ?")
            params.append(str(city))

    station = filters.get("station", "All stations")

    if (
        station
        and station != "All stations"
        and "station_id" in available_columns
    ):
        conditions.append("CAST(station_id AS VARCHAR) = ?")
        params.append(str(station))

    where_sql = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    return where_sql, params


def _query(sql, params=None):
    """Execute a query and return its small result as a DataFrame."""
    con = get_connection()

    try:
        return con.execute(
            sql,
            params or []
        ).fetchdf()

    finally:
        con.close()


def _filtered_source(filters=None):
    """
    Return a filtered SQL subquery and its parameters.
    Apply filters outside the station join to avoid
    ambiguous column references.
    """

    base = _base_query()

    where_sql, params = _filter_sql(
        filters,
        get_swap_columns()
    )

    return (
        f"(SELECT * FROM ({base}) AS base_filtered"
        f"{where_sql}) AS filtered",
        params
    )
# ---------------------------------------------------------
# 6. FILTER OPTIONS
# ---------------------------------------------------------

@st.cache_data(show_spinner="Reading filter options...")
def get_filter_options():
    """
    Return date bounds and distinct city/station options.

    Only distinct values and min/max dates are returned.
    """
    columns = get_swap_columns()

    if "event_ts" in columns:
        date_sql = """
            SELECT
                MIN(CAST(event_ts AS DATE)) AS min_date,
                MAX(CAST(event_ts AS DATE)) AS max_date
            FROM swap_data
        """
    else:
        date_sql = """
            SELECT
                NULL AS min_date,
                NULL AS max_date
        """

    con = get_connection()

    try:
        source = _base_query()

        con.execute(
            f"CREATE VIEW swap_data AS {source}"
        )

        dates = con.execute(date_sql).fetchone()

        city_options = ["All cities"]

        if "station_city" in con.execute(
            "DESCRIBE SELECT * FROM swap_data"
        ).fetchdf()["column_name"].tolist():
            cities = con.execute("""
                SELECT DISTINCT station_city
                FROM swap_data
                WHERE station_city IS NOT NULL
                ORDER BY station_city
            """).fetchall()

            city_options += [str(row[0]) for row in cities]

        elif "city" in columns:
            cities = con.execute("""
                SELECT DISTINCT city
                FROM swap_data
                WHERE city IS NOT NULL
                ORDER BY city
            """).fetchall()

            city_options += [str(row[0]) for row in cities]

        stations = []

        if "station_id" in columns:
            rows = con.execute("""
                SELECT DISTINCT CAST(station_id AS VARCHAR)
                FROM swap_data
                WHERE station_id IS NOT NULL
                ORDER BY 1
            """).fetchall()

            stations = [str(row[0]) for row in rows]

        return {
            "min_date": dates[0],
            "max_date": dates[1],
            "cities": city_options,
            "stations": ["All stations"] + stations,
        }

    finally:
        con.close()


# ---------------------------------------------------------
# 7. OVERVIEW KPIs
# ---------------------------------------------------------

def get_overview_kpis(filters=None):
    """
    Return Overview KPI values for the selected filters.

    Matches the original dashboard's event-row definitions.
    """
    source, params = _filtered_source(filters)
    columns = get_swap_columns()

    completed_expr = (
        "LOWER(TRIM(COALESCE(CAST(event_type AS VARCHAR), 'Missing'))) "
        f"= '{COMPLETED_LABEL}'"
        if "event_type" in columns
        else "FALSE"
    )

    station_expr = (
        "COUNT(DISTINCT station_id)"
        if "station_id" in columns
        else "NULL"
    )

    rider_expr = (
        "COUNT(DISTINCT rider_id)"
        if "rider_id" in columns
        else "NULL"
    )

    sql = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (
                WHERE {completed_expr}
            ) AS completed,
            COUNT(*) FILTER (
                WHERE NOT ({completed_expr})
            ) AS non_completed,
            {station_expr} AS unique_stations,
            {rider_expr} AS unique_riders
        FROM {source}
    """

    result = _query(sql, params)

    return result.iloc[0].to_dict()


# ---------------------------------------------------------
# 8. GENERIC GROUPED COUNTS
# ---------------------------------------------------------

def get_event_type_counts(filters=None):
    """Event type distribution for pie/bar charts."""
    source, params = _filtered_source(filters)

    if "event_type" not in get_swap_columns():
        return pd.DataFrame(
            columns=["event_type", "rows"]
        )

    sql = f"""
        SELECT
            LOWER(TRIM(
                COALESCE(CAST(event_type AS VARCHAR), 'Missing')
            )) AS event_type,
            COUNT(*) AS rows
        FROM {source}
        GROUP BY 1
        ORDER BY rows DESC
    """

    return _query(sql, params)


def get_tariff_counts(filters=None):
    """Tariff code counts, preserving missing values."""
    source, params = _filtered_source(filters)

    if "tariff_code" not in get_swap_columns():
        return pd.DataFrame(
            columns=["tariff_code", "rows"]
        )

    sql = f"""
        SELECT
            COALESCE(
                CAST(tariff_code AS VARCHAR),
                'Missing'
            ) AS tariff_code,
            COUNT(*) AS rows
        FROM {source}
        GROUP BY 1
        ORDER BY rows DESC
    """

    return _query(sql, params)


def get_daily_event_counts(filters=None):
    """Daily event-row counts."""
    source, params = _filtered_source(filters)

    if "event_ts" not in get_swap_columns():
        return pd.DataFrame(
            columns=["event_date", "event_rows"]
        )

    sql = f"""
        SELECT
            CAST(event_ts AS DATE) AS event_date,
            COUNT(*) AS event_rows
        FROM {source}
        WHERE event_ts IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """

    return _query(sql, params)


def get_hourly_event_counts(filters=None):
    """Event counts grouped by hour of day."""
    source, params = _filtered_source(filters)

    if "event_ts" not in get_swap_columns():
        return pd.DataFrame(
            columns=["event_hour", "event_rows"]
        )

    sql = f"""
        SELECT
            EXTRACT(HOUR FROM event_ts)::INTEGER AS event_hour,
            COUNT(*) AS event_rows
        FROM {source}
        WHERE event_ts IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """

    return _query(sql, params)


# ---------------------------------------------------------
# 9. STATION AGGREGATIONS
# ---------------------------------------------------------

def get_top_stations(filters=None, limit=10):
    """Top stations by number of event rows."""
    source, params = _filtered_source(filters)

    if "station_id" not in get_swap_columns():
        return pd.DataFrame(
            columns=["station_id", "event_rows"]
        )

    sql = f"""
        SELECT
            CAST(station_id AS VARCHAR) AS station_id,
            COUNT(*) AS event_rows
        FROM {source}
        WHERE station_id IS NOT NULL
        GROUP BY 1
        ORDER BY event_rows DESC
        LIMIT ?
    """

    return _query(sql, params + [int(limit)])


def get_station_summary(filters=None):
    """
    Station metrics equivalent to the original Stations page:
    event rows, completed event rows, amount, and average wait.
    """
    source, params = _filtered_source(filters)
    columns = get_swap_columns()

    if "station_id" not in columns:
        return pd.DataFrame()

    completed_expr = (
        f"COUNT(*) FILTER (WHERE LOWER(TRIM(COALESCE("
        f"CAST(event_type AS VARCHAR), 'Missing'))) "
        f"= '{COMPLETED_LABEL}')"
        if "event_type" in columns
        else "0"
    )

    amount_expr = (
        "SUM(amount_charged_inr)"
        if "amount_charged_inr" in columns
        else "NULL"
    )

    wait_expr = (
        "AVG(queue_wait_sec)"
        if "queue_wait_sec" in columns
        else "NULL"
    )

    sql = f"""
        SELECT
            CAST(station_id AS VARCHAR) AS station_id,
            COUNT(*) AS event_rows,
            {completed_expr} AS completed_event_rows,
            {amount_expr} AS amount_charged_sum_inr,
            {wait_expr} AS avg_queue_wait_sec
        FROM {source}
        WHERE station_id IS NOT NULL
        GROUP BY 1
        ORDER BY event_rows DESC
    """

    result = _query(sql, params)

    if not result.empty:
        result["completed_event_share_pct"] = (
            result["completed_event_rows"]
            / result["event_rows"]
            * 100
        )

    return result


# ---------------------------------------------------------
# 10. REVENUE AND QUEUE AGGREGATIONS
# ---------------------------------------------------------

def get_revenue_summary(filters=None):
    """Recorded amount, list price, and discount totals."""
    source, params = _filtered_source(filters)
    columns = get_swap_columns()

    expressions = []

    for col in [
        "amount_charged_inr",
        "list_price_inr",
        "discount_inr",
    ]:
        if col in columns:
            expressions.append(
                f"SUM({col}) AS {col}_sum"
            )
        else:
            expressions.append(
                f"NULL AS {col}_sum"
            )

    sql = f"""
        SELECT {", ".join(expressions)}
        FROM {source}
    """

    result = _query(sql, params)

    return result.iloc[0].to_dict()


def get_daily_revenue(filters=None):
    """Recorded amount charged, grouped by date."""
    source, params = _filtered_source(filters)

    columns = get_swap_columns()

    if (
        "event_ts" not in columns
        or "amount_charged_inr" not in columns
    ):
        return pd.DataFrame(
            columns=["event_date", "amount_charged_inr"]
        )

    sql = f"""
        SELECT
            CAST(event_ts AS DATE) AS event_date,
            SUM(amount_charged_inr) AS amount_charged_inr
        FROM {source}
        WHERE event_ts IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """

    return _query(sql, params)


def get_daily_queue_wait(filters=None):
    """Average recorded queue wait by date."""
    source, params = _filtered_source(filters)

    columns = get_swap_columns()

    if (
        "event_ts" not in columns
        or "queue_wait_sec" not in columns
    ):
        return pd.DataFrame(
            columns=["event_date", "queue_wait_sec"]
        )

    sql = f"""
        SELECT
            CAST(event_ts AS DATE) AS event_date,
            AVG(queue_wait_sec) AS queue_wait_sec
        FROM {source}
        WHERE event_ts IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """

    return _query(sql, params)


# ---------------------------------------------------------
# 11. DATA EXPLORER
# ---------------------------------------------------------

def get_filtered_rows(filters=None, columns=None, limit=1000):
    """
    Fetch a limited number of actual filtered swap-event rows.

    Use for the Data Explorer table and CSV download.
    Never use this to calculate dashboard-wide KPIs.
    """
    source, params = _filtered_source(filters)

    available = get_swap_columns()

    if columns:
        selected = [
            col for col in columns
            if col in available
        ]
    else:
        selected = available

    if not selected:
        return pd.DataFrame()

    # Column names come from the actual Parquet schema.
    select_sql = ", ".join(
        '"' + col.replace('"', '""') + '"'
        for col in selected
    )

    sql = f"""
        SELECT {select_sql}
        FROM {source}
        LIMIT ?
    """

    return _query(
        sql,
        params + [int(limit)]
    )

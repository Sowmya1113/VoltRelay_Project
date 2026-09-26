from pathlib import Path
import sys

import pandas as pd
import streamlit as st
import plotly.express as px


# =========================================================
# 1. PROJECT PATHS AND DATA LOADER
# =========================================================

HERE = Path(__file__).resolve().parent

PROJECT_ROOT = (
    HERE.parent
    if HERE.name.lower() == "dashboard"
    else HERE
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from Dashboard import data_loader as dl
except ModuleNotFoundError:
    import data_loader as dl


# =========================================================
# 2. VOLTRELAY COLOR PALETTE
# =========================================================

DARK = "#062D25"
DARKER = "#03251F"

GREEN = "#07845B"
MINT = "#49D6A1"

ORANGE = "#F4AD3D"
RED = "#E64B4B"

BLUE = "#2878D0"
PURPLE = "#8064C8"

BG = "#F4F7F6"
TEXT = "#172B3A"
MUTED = "#64748B"


# =========================================================
# 3. STREAMLIT PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="VoltRelay | Battery Swap Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================================
# 4. CUSTOM DASHBOARD STYLING
# =========================================================

st.markdown(
    f"""
    <style>

    @import url(
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
    );

    html, body, [class*="css"] {{
        font-family: Inter, sans-serif;
    }}

    .stApp {{
        background: {BG};
        color: {TEXT};
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(
            180deg,
            {DARKER},
            {DARK}
        );
    }}

    [data-testid="stSidebar"] * {{
        color: #F4FBF8 !important;
    }}

    .brand {{
        font-size: 1.8rem;
        font-weight: 800;
        letter-spacing: -.8px;
        margin-bottom: 0;
    }}

    .brand-sub {{
        color: #B8D7CC;
        font-size: .85rem;
        margin-top: -5px;
    }}

    .page-title {{
        font-size: 2.1rem;
        font-weight: 800;
        letter-spacing: -1px;
        margin-bottom: 0;
        color: {TEXT};
    }}

    .page-subtitle {{
        color: {MUTED};
        margin-top: -4px;
        margin-bottom: 1rem;
    }}

    div[data-testid="stPlotlyChart"] {{
        background: white;
        border-radius: 12px;
        border: 1px solid #E6ECE9;
        padding: 5px;
    }}

    footer {{
        visibility: hidden;
    }}

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# 5. SIDEBAR NAVIGATION
# =========================================================

PAGES = [
    "Overview",
    "Swap Operations",
    "Revenue & Payments",
    "Stations",
    "Riders",
    "Battery Performance",
    "Data Explorer",
    "About"
]

with st.sidebar:

    st.markdown(
        '<div class="brand">⚡ VoltRelay</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="brand-sub">Battery Swap Analytics</div>',
        unsafe_allow_html=True
    )

    st.markdown("---")

    page = st.radio(
        "NAVIGATION",
        PAGES,
        label_visibility="visible"
    )

    st.markdown("---")

    st.caption(
        "Connected to local cleaned project data"
    )


# =========================================================
# 6. LOAD GLOBAL FILTER OPTIONS
# =========================================================

@st.cache_data(show_spinner=False)
def filter_options():
    return dl.get_filter_options()


try:

    options = filter_options()

except Exception as exc:

    st.error(
        "Could not connect to the cleaned swap-event data. "
        "Confirm that data_loader.py is in Dashboard and "
        "the data folder is in the project root."
    )

    st.exception(exc)

    st.stop()


# =========================================================
# 7. GLOBAL FILTERS
# =========================================================

min_date = options.get("min_date")
max_date = options.get("max_date")

c1, c2, c3 = st.columns([1.3, 1, 1])


# -------------------------
# Event date range
# -------------------------

with c1:

    if min_date is not None and max_date is not None:

        date_range = st.date_input(
            "Event date range",
            value=(
                pd.Timestamp(min_date).date(),
                pd.Timestamp(max_date).date()
            ),
            min_value=pd.Timestamp(min_date).date(),
            max_value=pd.Timestamp(max_date).date()
        )

        if (
            not isinstance(date_range, (tuple, list))
            or len(date_range) != 2
        ):

            start_date = pd.Timestamp(
                min_date
            ).date()

            end_date = pd.Timestamp(
                max_date
            ).date()

        else:

            start_date, end_date = date_range

    else:

        start_date = None
        end_date = None

        st.caption(
            "No event timestamp range available"
        )


# -------------------------
# City filter
# -------------------------

with c2:

    cities = options.get(
        "cities",
        ["All cities"]
    )

    city = st.selectbox(
        "City",
        cities if cities else ["All cities"]
    )


# -------------------------
# Station filter
# -------------------------

with c3:

    stations = options.get(
        "stations",
        ["All stations"]
    )

    station = st.selectbox(
        "Station",
        stations if stations else ["All stations"]
    )


# Global filters passed to data_loader.py

filters = {
    "start_date": start_date,
    "end_date": end_date,
    "city": city,
    "station": station
}


# =========================================================
# 8. DASHBOARD HEADER
# =========================================================

st.markdown(
    '<div class="page-title">VoltRelay Dashboard</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="page-subtitle">'
    'Operational performance, revenue, and battery-swap insights'
    '</div>',
    unsafe_allow_html=True
)


# =========================================================
# 9. HELPER FUNCTIONS
# =========================================================

def money(v):

    try:

        return (
            "₹" + f"{float(v):,.0f}"
            if pd.notna(v)
            else "—"
        )

    except (TypeError, ValueError):

        return "—"


def num(v):

    try:

        return (
            f"{int(float(v)):,}"
            if pd.notna(v)
            else "—"
        )

    except (TypeError, ValueError):

        return "—"


def metric(label, value, help_text=""):

    st.metric(
        label,
        value,
        help=help_text or None
    )


def chart(fig, height=350):

    fig.update_layout(
        height=height,
        paper_bgcolor="white",
        plot_bgcolor="white",

        margin=dict(
            l=25,
            r=25,
            t=60,
            b=60
        ),

        font=dict(
            family="Inter, sans-serif",
            color=TEXT
        ),

        legend=dict(
            orientation="h",
            yanchor="top",
            y=-.2,
            xanchor="center",
            x=.5
        )
    )

    fig.update_xaxes(
        showgrid=False,
        linecolor="#E5ECE9"
    )

    fig.update_yaxes(
        gridcolor="#E5ECE9",
        zeroline=False
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


def empty(df, message):

    if df is None or df.empty:

        st.info(message)

        return True

    return False


# =========================================================
# 10. OVERVIEW PAGE
# =========================================================

if page == "Overview":

    # -----------------------------------------------------
    # Overview KPIs
    # -----------------------------------------------------

    k = dl.get_overview_kpis(filters)

    total = k.get("total", 0) or 0

    completed = (
        k.get("completed", 0) or 0
    )

    non_completed = (
        k.get("non_completed", 0) or 0
    )

    completed_pct = (
        completed / total * 100
        if total
        else 0
    )

    cards = st.columns(5)

    with cards[0]:

        metric(
            "Total Event Rows",
            num(total)
        )

    with cards[1]:

        metric(
            "Completed Swap Events",
            num(completed),
            f"{completed_pct:.2f}% of filtered event rows"
        )

    with cards[2]:

        metric(
            "Other Event Rows",
            num(non_completed)
        )

    with cards[3]:

        metric(
            "Unique Stations",
            num(k.get("unique_stations"))
        )

    with cards[4]:

        metric(
            "Unique Riders",
            num(k.get("unique_riders"))
        )


    # -----------------------------------------------------
    # Daily and hourly event charts
    # -----------------------------------------------------

    a, b = st.columns(2)

    with a:

        daily = dl.get_daily_event_counts(
            filters
        )

        if not empty(
            daily,
            "Daily event volume is unavailable for these filters."
        ):

            fig = px.line(
                daily,
                x="event_date",
                y="event_rows",
                title="Daily Swap Event Volume",
                labels={
                    "event_date": "Date",
                    "event_rows": "Event rows"
                }
            )

            fig.update_traces(
                line_color=GREEN,
                line_width=2
            )

            chart(fig)


    with b:

        hourly = dl.get_hourly_event_counts(
            filters
        )

        if not empty(
            hourly,
            "Hourly event volume is unavailable for these filters."
        ):

            fig = px.bar(
                hourly,
                x="event_hour",
                y="event_rows",
                title="Event Volume by Hour",
                labels={
                    "event_hour": "Hour of day",
                    "event_rows": "Event rows"
                },
                color_discrete_sequence=[GREEN]
            )

            fig.update_xaxes(
                dtick=1
            )

            chart(fig)


    # -----------------------------------------------------
    # Event types, tariffs, and Top 10 stations
    # -----------------------------------------------------

    a, b, c = st.columns(3)


    # Event type distribution

    with a:

        counts = dl.get_event_type_counts(
            filters
        )

        if not empty(
            counts,
            "Event type breakdown is unavailable."
        ):

            fig = px.pie(
                counts,
                names="event_type",
                values="rows",
                hole=.55,
                title="Event Type Distribution",
                color_discrete_sequence=[
                    GREEN,
                    ORANGE,
                    RED,
                    PURPLE,
                    BLUE,
                    MINT
                ]
            )

            chart(
                fig,
                370
            )


    # Tariff distribution

    with b:

        tariffs = dl.get_tariff_counts(
            filters
        )

        if not empty(
            tariffs,
            "Tariff code breakdown is unavailable."
        ):

            fig = px.pie(
                tariffs,
                names="tariff_code",
                values="rows",
                hole=.55,
                title="Tariff Code Distribution",
                color_discrete_sequence=[
                    GREEN,
                    BLUE,
                    ORANGE,
                    RED,
                    PURPLE
                ]
            )

            chart(
                fig,
                370
            )


    # -----------------------------------------------------
    # TOP 10 STATIONS
    # -----------------------------------------------------

    with c:

        # Keep date and city filters.
        # Ignore the individual station filter so that
        # multiple stations can appear in the ranking.

        top_filters = filters.copy()

        top_filters["station"] = "All stations"

        top = dl.get_top_stations(
            top_filters,
            limit=10
        )

        if not empty(
            top,
            "Station ranking is unavailable."
        ):

            # Remove missing station IDs.

            top = (
                top.dropna(
                    subset=["station_id"]
                )
                .sort_values(
                    "event_rows",
                    ascending=True
                )
            )

            # Build horizontal bar chart.

            fig = px.bar(
                top,
                x="event_rows",
                y="station_id",
                orientation="h",

                title=(
                    f"Top {len(top)} "
                    "Stations by Event Rows"
                ),

                labels={
                    "event_rows": "Event rows",
                    "station_id": "Station"
                },

                text="event_rows",

                color_discrete_sequence=[
                    GREEN
                ]
            )

            # Display event counts on bars.

            fig.update_traces(
                texttemplate="%{x:,}",
                textposition="outside",
                cliponaxis=False
            )

            # Set the chart height dynamically.

            fig.update_layout(
                height=max(
                    370,
                    42 * len(top) + 120
                ),

                yaxis={
                    "type": "category",
                    "categoryorder": "array",
                    "categoryarray": (
                        top["station_id"].tolist()
                    ),
                    "automargin": True
                },

                xaxis_title="Event rows",
                yaxis_title="Station"
            )

            chart(
                fig,
                max(
                    370,
                    42 * len(top) + 120
                )
            )


# =========================================================
# 11. SWAP OPERATIONS PAGE
# =========================================================

elif page == "Swap Operations":

    st.subheader(
        "Swap Operations"
    )

    a, b = st.columns(2)


    # Event type analysis

    with a:

        counts = dl.get_event_type_counts(
            filters
        )

        if not empty(
            counts,
            "Event type data is unavailable."
        ):

            fig = px.bar(
                counts,
                x="event_type",
                y="rows",

                title="Recorded Event Outcomes",

                labels={
                    "event_type": "Event type",
                    "rows": "Event rows"
                },

                color_discrete_sequence=[
                    GREEN
                ]
            )

            chart(fig)


    # Daily event volume

    with b:

        daily = dl.get_daily_event_counts(
            filters
        )

        if not empty(
            daily,
            "Daily operations data is unavailable."
        ):

            fig = px.area(
                daily,
                x="event_date",
                y="event_rows",

                title="Daily Event Mix / Volume",

                labels={
                    "event_date": "Date",
                    "event_rows": "Event rows"
                },

                color_discrete_sequence=[
                    GREEN
                ]
            )

            chart(fig)


    # Queue wait analysis

    q = dl.get_daily_queue_wait(
        filters
    )

    if not empty(
        q,
        "Recorded queue-wait data is unavailable."
    ):

        fig = px.line(
            q,
            x="event_date",
            y="queue_wait_sec",

            title="Average Recorded Queue Wait",

            labels={
                "event_date": "Date",
                "queue_wait_sec": "Queue wait (seconds)"
            },

            color_discrete_sequence=[
                ORANGE
            ]
        )

        chart(fig)


# =========================================================
# 12. REVENUE AND PAYMENTS PAGE
# =========================================================

elif page == "Revenue & Payments":

    st.subheader(
        "Revenue & Payments"
    )

    rev = dl.get_revenue_summary(
        filters
    )

    a, b, c = st.columns(3)

    with a:

        metric(
            "Recorded Amount Charged",
            money(
                rev.get(
                    "amount_charged_inr_sum"
                )
            )
        )

    with b:

        metric(
            "Recorded List Price",
            money(
                rev.get(
                    "list_price_inr_sum"
                )
            )
        )

    with c:

        metric(
            "Recorded Discounts",
            money(
                rev.get(
                    "discount_inr_sum"
                )
            )
        )


    # Daily revenue

    daily = dl.get_daily_revenue(
        filters
    )

    if not empty(
        daily,
        "Daily amount-charged data is unavailable."
    ):

        fig = px.bar(
            daily,
            x="event_date",
            y="amount_charged_inr",

            title=(
                "Amount Charged by Event Date "
                "(as recorded)"
            ),

            labels={
                "event_date": "Date",
                "amount_charged_inr": (
                    "Amount charged (INR)"
                )
            },

            color_discrete_sequence=[
                GREEN
            ]
        )

        chart(fig)


    # Tariff breakdown

    tariffs = dl.get_tariff_counts(
        filters
    )

    if not empty(
        tariffs,
        "Tariff breakdown is unavailable."
    ):

        fig = px.bar(
            tariffs,
            x="tariff_code",
            y="rows",

            title="Event Rows by Tariff Code",

            labels={
                "tariff_code": "Tariff code",
                "rows": "Event rows"
            },

            color_discrete_sequence=[
                BLUE
            ]
        )

        chart(fig)


    st.caption(
        "Payment-mode fields are not inferred. "
        "Amounts and tariff categories reflect "
        "the recorded source data."
    )


# =========================================================
# 13. STATIONS PAGE
# =========================================================

elif page == "Stations":

    st.subheader(
        "Station Performance"
    )

    # -----------------------------------------------------
    # Station filters
    # -----------------------------------------------------

    # Keep date and city filters.
    # Ignore the selected individual station because
    # this page compares multiple stations.

    station_filters = filters.copy()

    station_filters["station"] = "All stations"


    # -----------------------------------------------------
    # Load station summary
    # -----------------------------------------------------

    summary = dl.get_station_summary(
        station_filters
    )

    if not empty(
        summary,
        "Station summary is unavailable. "
        "Check that station_id exists in the swap data."
    ):

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True
        )


        # -------------------------------------------------
        # TOP 15 STATIONS CHART
        # -------------------------------------------------

        if (
            "event_rows" in summary
            and "station_id" in summary
        ):

            # Remove rows without station IDs,
            # select the 15 highest event counts,
            # then sort for horizontal plotting.

            top = (
                summary.dropna(
                    subset=["station_id"]
                )
                .nlargest(
                    15,
                    "event_rows"
                )
                .sort_values(
                    "event_rows",
                    ascending=True
                )
            )


            if not top.empty:

                fig = px.bar(
                    top,

                    x="event_rows",
                    y="station_id",

                    orientation="h",

                    title=(
                        f"Top {len(top)} "
                        "Stations by Event Rows"
                    ),

                    labels={
                        "event_rows": "Event rows",
                        "station_id": "Station"
                    },

                    text="event_rows",

                    color_discrete_sequence=[
                        GREEN
                    ]
                )


                # Add counts outside each bar.

                fig.update_traces(
                    texttemplate="%{x:,}",
                    textposition="outside",
                    cliponaxis=False
                )


                # Set chart height and category order.

                fig.update_layout(
                    height=max(
                        450,
                        42 * len(top) + 120
                    ),

                    yaxis={
                        "type": "category",
                        "categoryorder": "array",
                        "categoryarray": (
                            top["station_id"].tolist()
                        ),
                        "automargin": True
                    },

                    xaxis_title="Event rows",
                    yaxis_title="Station"
                )


                chart(
                    fig,
                    max(
                        450,
                        42 * len(top) + 120
                    )
                )

            else:

                st.info(
                    "No station rows match the "
                    "selected date and city filters."
                )


# =========================================================
# 14. RIDERS PAGE
# =========================================================

elif page == "Riders":

    st.subheader(
        "Rider Data"
    )

    riders_df = dl.load_riders()

    if not empty(
        riders_df,
        "Rider reference file is missing or empty."
    ):

        st.metric(
            "Rider Records",
            f"{len(riders_df):,}"
        )

        st.dataframe(
            riders_df.head(1000),
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "Showing up to 1,000 reference rows. "
            "Swap-event filtering does not necessarily "
            "filter this reference table."
        )


# =========================================================
# 15. BATTERY PERFORMANCE PAGE
# =========================================================

elif page == "Battery Performance":

    st.subheader(
        "Battery Performance"
    )

    batteries_df = dl.load_batteries()

    if not empty(
        batteries_df,
        "Battery reference file is missing or empty."
    ):

        st.metric(
            "Battery Records",
            f"{len(batteries_df):,}"
        )

        st.dataframe(
            batteries_df.head(1000),
            use_container_width=True,
            hide_index=True
        )


    # Station-hourly telemetry

    telemetry = dl.load_telemetry()

    if not empty(
        telemetry,
        "Station-hourly telemetry file is missing or empty."
    ):

        st.markdown(
            "#### Station-hourly telemetry (sample)"
        )

        st.dataframe(
            telemetry.head(1000),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# 16. DATA EXPLORER PAGE
# =========================================================

elif page == "Data Explorer":

    st.subheader(
        "Data Explorer"
    )

    try:

        columns = dl.get_swap_columns()

        defaults = columns[
            :min(10, len(columns))
        ]

        selected = st.multiselect(
            "Columns to display",
            columns,
            default=defaults
        )

        limit = st.select_slider(
            "Maximum rows",
            options=[
                100,
                500,
                1000,
                2500,
                5000
            ],
            value=1000
        )


        # Retrieve filtered event records

        rows = dl.get_filtered_rows(
            filters,
            columns=selected,
            limit=limit
        )


        if not empty(
            rows,
            "No rows returned for the selected filters and columns."
        ):

            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True
            )


            # CSV download

            csv = rows.to_csv(
                index=False
            ).encode("utf-8")

            st.download_button(
                "Download displayed rows as CSV",

                data=csv,

                file_name=(
                    "voltrelay_filtered_events.csv"
                ),

                mime="text/csv"
            )


        st.caption(
            "The table is limited to the selected row cap; "
            "dashboard-wide KPIs are computed in DuckDB "
            "over the filtered data."
        )


    except Exception as exc:

        st.error(
            "Could not load the Data Explorer."
        )

        st.exception(exc)


# =========================================================
# 17. ABOUT PAGE
# =========================================================

else:

    st.subheader(
        "About VoltRelay Analytics"
    )

    st.markdown(
        """
        This dashboard summarizes the cleaned VoltRelay
        battery-swap project data.

        - Swap-event analytics are queried through DuckDB
          from the Parquet parts.

        - Reference pages display available cleaned
          reference files.

        - Missing source files or fields are reported
          rather than replaced with synthetic values.

        - Counts are event-row counts unless the label
          explicitly says completed swaps or unique entities.
        """
    )
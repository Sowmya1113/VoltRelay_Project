"""Add validated KPI functions here.

Keep each KPI's business definition, numerator, denominator, filters,
and source tables documented. Do not calculate final KPIs from unvalidated
or duplicated transaction data.
"""

import pandas as pd


def completed_swap_count(swap_events: pd.DataFrame) -> int:
    """Count completed swaps using the project's verified event-type definition."""
    if "event_type" not in swap_events.columns:
        raise KeyError("swap_events must contain event_type")
    return int(swap_events["event_type"].astype("string").str.lower()
               .eq("swap_completed").sum())

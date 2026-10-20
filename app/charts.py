"""Picks a sensible default chart for a query result, or none."""
import pandas as pd

TIME_HINTS = ("month", "date", "year", "week", "quarter", "day")


def suggest_chart(df: pd.DataFrame):
    """Return (kind, x, y) for line/bar charts, or None if a table is the better view."""
    if df is None or len(df) < 2 or len(df) > 60 or df.shape[1] < 2:
        return None
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    labels = [c for c in df.columns if c not in numeric]
    x = None
    for c in df.columns:
        if any(h in c.lower() for h in TIME_HINTS) or pd.api.types.is_datetime64_any_dtype(df[c]):
            x = c
            break
    y_cols = [c for c in numeric if c != x]
    if not y_cols:
        return None
    y = y_cols[0]
    if x is not None:
        return ("line", x, y)
    if labels:
        return ("bar", labels[0], y)
    return None

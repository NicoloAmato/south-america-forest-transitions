"""Compare a local area table with a reference table."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PIXEL_COLUMNS = ("FIN_NODATA", "FIN_0", "FIN_1", "FIN_10", "FIN_20", "FIN_30")


def compare_tables(reference: Path, candidate: Path) -> pd.DataFrame:
    """Return signed pixel differences (candidate minus reference) by GADM code."""
    old = pd.read_csv(reference).set_index("GID_0")
    new = pd.read_csv(candidate).set_index("GID_0")
    if not old.index.is_unique or not new.index.is_unique:
        raise ValueError("each table must contain at most one row per GADM code")
    if set(old.index) != set(new.index):
        raise ValueError(
            f"Different territories. Missing: {sorted(set(old.index) - set(new.index))}; "
            f"extra: {sorted(set(new.index) - set(old.index))}"
        )
    columns = list(PIXEL_COLUMNS)
    differences = new.loc[old.index, columns] - old[columns]
    differences.columns = [f"delta_{column}" for column in columns]
    differences["delta_total_px"] = differences.sum(axis=1)
    return differences

"""Zonal statistics: pixels of each class inside each country.

Counterpart of the QGIS "Zonal histogram" tool followed by the Field Calculator that
converted pixel counts to square kilometres.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from rasterio.features import rasterize

from . import config
from .grid import Grid

_CHUNK_ROWS = 1024


def rasterize_zones(geometries: Sequence, grid: Grid) -> np.ndarray:
    """Label every grid pixel with the 1-based index of the polygon containing its centre.

    Pixels outside all polygons get 0. The pixel-centre rule is the one used by the QGIS
    zonal histogram.
    """
    if len(geometries) > 254:
        raise ValueError("at most 254 zones are supported")
    shapes = [(geometry, index) for index, geometry in enumerate(geometries, start=1)]
    return rasterize(
        shapes,
        out_shape=grid.shape,
        transform=grid.transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )


def zonal_histogram(values: np.ndarray, zones: np.ndarray, n_zones: int) -> np.ndarray:
    """Count the pixels of every value (0-255) in every zone.

    Returns an array of shape ``(n_zones, 256)``; row ``i`` belongs to zone ``i + 1``.
    """
    if values.shape != zones.shape:
        raise ValueError("values and zones must have the same shape")
    if values.dtype != np.uint8:
        raise TypeError("values must be uint8")
    counts = np.zeros((n_zones + 1) * 256, dtype=np.int64)
    for start in range(0, values.shape[0], _CHUNK_ROWS):
        stop = start + _CHUNK_ROWS
        combined = zones[start:stop].astype(np.int32) * 256 + values[start:stop]
        counts += np.bincount(combined.ravel(), minlength=counts.size)
    return counts.reshape(n_zones + 1, 256)[1:]


def change_table(histogram: np.ndarray, countries: pd.DataFrame) -> pd.DataFrame:
    """Per-country table of pixel counts and areas by class.

    ``FIN_<code>`` are pixel counts of the final map; the ``*_km2`` columns are areas
    (count x 0.25 km2, the area of a 500 m pixel).
    """
    table = countries[["fid", "GID_0", "COUNTRY"]].reset_index(drop=True).copy()
    table["FIN_NODATA"] = histogram[:, config.NODATA]
    for code in (config.OTHER, config.DEFORESTATION, config.IMPROVED, config.STABLE,
                 config.DEGRADED):  # fmt: skip
        table[f"FIN_{code}"] = histogram[:, code]
    area = config.PIXEL_AREA_KM2
    table["DEFOR_km2"] = table[f"FIN_{config.DEFORESTATION}"] * area
    table["MIGL_km2"] = table[f"FIN_{config.IMPROVED}"] * area
    table["STAB_km2"] = table[f"FIN_{config.STABLE}"] * area
    table["DEGR_km2"] = table[f"FIN_{config.DEGRADED}"] * area
    return table

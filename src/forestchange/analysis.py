"""The raster algebra of the analysis.

Each function is the counterpart of one Raster Calculator / Reclassify step of the
QGIS workflow (the expression is quoted in the docstring). They work on
plain NumPy arrays, so they can be tested without any geodata.
"""

from __future__ import annotations

import numpy as np

from . import config


def ndvi(red: np.ndarray, nir: np.ndarray, fill: int = config.REFLECTANCE_FILL) -> np.ndarray:
    """Normalised difference vegetation index, NaN where it is undefined.

    QGIS: ``("raster_NIR@1" - "raster_RED@1") / ("raster_NIR@1" + "raster_RED@1")``

    The MOD09Q1 scale factor (0.0001) cancels out, so the raw integers are used directly,
    and the resulting index is stored as float32.
    """
    red_f = red.astype(np.float64)
    nir_f = nir.astype(np.float64)
    total = nir_f + red_f
    valid = (red != fill) & (nir != fill) & (total != 0)
    out = np.full(red.shape, np.nan, dtype=np.float64)
    np.divide(nir_f - red_f, total, out=out, where=valid)
    return out.astype(np.float32)


def ndvi_change(ndvi_start: np.ndarray, ndvi_end: np.ndarray) -> np.ndarray:
    """NDVI difference between the two years (float32, NaN where either is undefined).

    QGIS: ``"NDVI_2021@1" - "NDVI_2001@1"``
    """
    return (ndvi_end.astype(np.float64) - ndvi_start.astype(np.float64)).astype(np.float32)


def is_forest(land_cover: np.ndarray) -> np.ndarray:
    """True where the IGBP class is a forest class (1-5).

    QGIS: ``"LC@1" >= 1 AND "LC@1" <= 5``
    """
    return (land_cover >= config.FOREST_CLASS_MIN) & (land_cover <= config.FOREST_CLASS_MAX)


def stable_forest(lc_start: np.ndarray, lc_end: np.ndarray) -> np.ndarray:
    """Forest in both years (``Maschera_Foreste_Stabili``)."""
    return is_forest(lc_start) & is_forest(lc_end)


def structural_deforestation(lc_start: np.ndarray, lc_end: np.ndarray) -> np.ndarray:
    """Forest in the first year, any other class in the last (``Maschera_Deforestazione``).

    QGIS: ``("LC_2001" >= 1 AND "LC_2001" <= 5) AND ("LC_2021" > 5 OR "LC_2021" = 0)``
    """
    return is_forest(lc_start) & ((lc_end > config.FOREST_CLASS_MAX) | (lc_end == 0))


def classify_ndvi_change(
    change: np.ndarray,
    threshold: float = config.NDVI_CHANGE_THRESHOLD,
    limit: float = config.NDVI_CHANGE_LIMIT,
) -> np.ndarray:
    """Reclassify the NDVI difference into degraded / stable / improved.

    Both threshold endpoints belong to the stable class:
    ``[-2, -0.1) -> 30``, ``[-0.1, 0.1] -> 20``, ``(0.1, 2] -> 10``.
    Values outside the table (including NaN) get 0, meaning "not classified".
    """
    value = np.asarray(change, dtype=np.float32)
    threshold = np.float32(threshold)
    out = np.zeros(value.shape, dtype=np.uint8)
    out[(value >= -limit) & (value < -threshold)] = config.DEGRADED
    out[(value >= -threshold) & (value <= threshold)] = config.STABLE
    out[(value > threshold) & (value <= limit)] = config.IMPROVED
    return out


def forest_change(
    lc_start: np.ndarray,
    lc_end: np.ndarray,
    change: np.ndarray,
    lc_fill: int = config.LAND_COVER_FILL,
) -> np.ndarray:
    """The final thematic map (``Mappa_Finale_Cambiamento_Forestale``).

    ====== =======================================================================
    code   meaning
    ====== =======================================================================
    1      structural deforestation: forest in the first year, not in the last
    10     stable forest, NDVI change above +0.1 (improvement)
    20     stable forest, NDVI change within +/-0.1 (stable)
    30     stable forest, NDVI change below -0.1 (degradation)
    0      everything else: never forest, or forest only in the last year
    255    no data: land cover missing, or stable forest with an undefined NDVI change
    ====== =======================================================================

    QGIS: ``("Maschera_Deforestazione@1" = 1) * 1 + ("Maschera_Deforestazione@1" != 1) *
    "Cambiamento_Condizione@1"``, then multiplied by the mask of the pixels that were
    forest in at least one year.
    """
    stable = stable_forest(lc_start, lc_end)
    condition = classify_ndvi_change(change)

    out = np.full(lc_start.shape, config.OTHER, dtype=np.uint8)
    out[stable] = condition[stable]
    out[stable & (condition == 0)] = config.NODATA
    out[structural_deforestation(lc_start, lc_end)] = config.DEFORESTATION
    out[(lc_start == lc_fill) | (lc_end == lc_fill)] = config.NODATA
    return out


# Codes of the land-cover-only transition map, used to check the forest transition counts
# independently of the NDVI composites.
NEVER_FOREST = 0
FOREST_LOSS = 1
FOREST_STABLE = 2
FOREST_GAIN = 3


def forest_transitions(
    lc_start: np.ndarray, lc_end: np.ndarray, lc_fill: int = config.LAND_COVER_FILL
) -> np.ndarray:
    """Forest / non-forest transition between the two land cover maps (diagnostic)."""
    start = is_forest(lc_start)
    end = is_forest(lc_end)
    out = np.full(lc_start.shape, NEVER_FOREST, dtype=np.uint8)
    out[start & ~end] = FOREST_LOSS
    out[start & end] = FOREST_STABLE
    out[~start & end] = FOREST_GAIN
    out[(lc_start == lc_fill) | (lc_end == lc_fill)] = config.NODATA
    return out

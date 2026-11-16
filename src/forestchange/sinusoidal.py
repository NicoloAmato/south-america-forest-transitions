"""Geometry of the MODIS sinusoidal tile grid.

MODIS land products are distributed as 36 x 18 square tiles ("hXXvYY") in a sinusoidal
projection on a sphere. The grid is completely regular, so the position of every pixel
follows from the tile indices and the number of pixels per tile side.
"""

from __future__ import annotations

import math
import re

EARTH_RADIUS_M = 6371007.181
SINUSOIDAL_PROJ4 = "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"

TILES_HORIZONTAL = 36
TILES_VERTICAL = 18
TILE_SIZE_M = 2 * math.pi * EARTH_RADIUS_M / TILES_HORIZONTAL  # ~1111950.52 m
GLOBAL_X_MIN = -math.pi * EARTH_RADIUS_M  # western edge of tile column h00
GLOBAL_Y_MAX = math.pi * EARTH_RADIUS_M / 2  # northern edge of tile row v00

_TILE_PATTERN = re.compile(r"\.h(\d{2})v(\d{2})\.")
_DATE_PATTERN = re.compile(r"\.A(\d{4})(\d{3})\.")


def parse_tile(name: str) -> tuple[int, int]:
    """Horizontal and vertical tile index from a MODIS file name.

    >>> parse_tile("MCD12Q1.A2001001.h12v09.061.2022146033342.hdf")
    (12, 9)
    """
    match = _TILE_PATTERN.search(name)
    if match is None:
        raise ValueError(f"no hXXvYY tile identifier in {name!r}")
    return int(match.group(1)), int(match.group(2))


def parse_acquisition(name: str) -> tuple[int, int]:
    """Year and day of year from a MODIS file name.

    >>> parse_acquisition("MOD09Q1.A2021209.h12v09.061.2021218050924.hdf")
    (2021, 209)
    """
    match = _DATE_PATTERN.search(name)
    if match is None:
        raise ValueError(f"no AYYYYDDD acquisition date in {name!r}")
    return int(match.group(1)), int(match.group(2))


def tile_bounds(h: int, v: int) -> tuple[float, float, float, float]:
    """Bounds (x_min, y_min, x_max, y_max) of a tile in sinusoidal metres."""
    if not (0 <= h < TILES_HORIZONTAL and 0 <= v < TILES_VERTICAL):
        raise ValueError(f"tile h{h:02d}v{v:02d} does not exist")
    x_min = GLOBAL_X_MIN + h * TILE_SIZE_M
    y_max = GLOBAL_Y_MAX - v * TILE_SIZE_M
    return x_min, y_max - TILE_SIZE_M, x_min + TILE_SIZE_M, y_max

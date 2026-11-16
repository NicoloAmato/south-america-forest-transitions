"""The regular grid on which every raster of the analysis is stored."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from affine import Affine

from . import config


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid with square pixels."""

    crs: str
    x_min: float
    y_max: float
    pixel_size: float
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def x_max(self) -> float:
        return self.x_min + self.width * self.pixel_size

    @property
    def y_min(self) -> float:
        return self.y_max - self.height * self.pixel_size

    @property
    def transform(self) -> Affine:
        return Affine(self.pixel_size, 0.0, self.x_min, 0.0, -self.pixel_size, self.y_max)

    def x_centres(self, start: int = 0, stop: int | None = None) -> np.ndarray:
        """X coordinates of the pixel centres of columns ``start..stop``."""
        cols = np.arange(start, self.width if stop is None else stop)
        return self.x_min + (cols + 0.5) * self.pixel_size

    def y_centres(self, start: int = 0, stop: int | None = None) -> np.ndarray:
        """Y coordinates of the pixel centres of rows ``start..stop``."""
        rows = np.arange(start, self.height if stop is None else stop)
        return self.y_max - (rows + 0.5) * self.pixel_size

    def window(
        self, x_min: float, y_min: float, x_max: float, y_max: float, pad: int = 0
    ) -> tuple[slice, slice] | None:
        """Rows and columns covering a bounding box, or ``None`` if it misses the grid."""
        col0 = max(math.floor((x_min - self.x_min) / self.pixel_size) - pad, 0)
        col1 = min(math.ceil((x_max - self.x_min) / self.pixel_size) + pad, self.width)
        row0 = max(math.floor((self.y_max - y_max) / self.pixel_size) - pad, 0)
        row1 = min(math.ceil((self.y_max - y_min) / self.pixel_size) + pad, self.height)
        if col0 >= col1 or row0 >= row1:
            return None
        return slice(row0, row1), slice(col0, col1)


def analysis_grid() -> Grid:
    """The 500 m equal-area grid of the analysis (see ``config``)."""
    return Grid(
        crs=config.TARGET_CRS,
        x_min=config.GRID_X_MIN,
        y_max=config.GRID_Y_MAX,
        pixel_size=config.PIXEL_SIZE_M,
        width=config.GRID_WIDTH,
        height=config.GRID_HEIGHT,
    )

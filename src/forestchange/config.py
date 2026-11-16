"""Parameters of the analysis.

The inputs, grid and classification settings are shared across the analysis and figures.
"""

from __future__ import annotations

# --- Study period ---------------------------------------------------------------------
YEAR_START = 2001
YEAR_END = 2021

# --- Input products (NASA LP DAAC, MODIS collection 6.1) --------------------------------
MODIS_VERSION = "061"
LAND_COVER_PRODUCT = "MCD12Q1"  # yearly land cover type, 500 m
LAND_COVER_LAYER = "LC_Type1"  # IGBP classification scheme
LAND_COVER_FILL = 255
REFLECTANCE_PRODUCT = "MOD09Q1"  # 8-day surface reflectance composite, 250 m
RED_LAYER = "sur_refl_b01"
NIR_LAYER = "sur_refl_b02"
REFLECTANCE_FILL = -28672

# First day of the 8-day MOD09Q1 composite used to compute the NDVI of each year.
NDVI_COMPOSITE_START = {YEAR_START: "2001-07-28", YEAR_END: "2021-07-28"}

# Longitude/latitude rectangle (west, south, east, north) used to search for MODIS tiles.
SEARCH_BBOX = (-82.0, -56.5, -34.0, 13.5)

# --- Study area ---------------------------------------------------------------------------
# GADM 4.1 level-0 units, in the order used for the country table.
COUNTRIES = (
    "ARG", "BOL", "BRA", "CHL", "COL", "ECU", "GUF", "GUY", "PER", "PRY", "SUR", "URY", "VEN",
)  # fmt: skip
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_{iso}_shp.zip"

# --- Analysis grid ------------------------------------------------------------------------
TARGET_CRS = "ESRI:102033"  # South America Albers Equal Area Conic
PIXEL_SIZE_M = 500.0
PIXEL_AREA_KM2 = (PIXEL_SIZE_M / 1000.0) ** 2  # 0.25 km2

# Fixed extent of the equal-area analysis grid, aligned to whole pixels.
GRID_X_MIN = -4_570_000.0
GRID_Y_MAX = 5_239_000.0
GRID_WIDTH = 15_280
GRID_HEIGHT = 15_690

# --- Classification -----------------------------------------------------------------------
FOREST_CLASS_MIN = 1  # IGBP classes 1-5: evergreen/deciduous needleleaf and broadleaf, mixed
FOREST_CLASS_MAX = 5
NDVI_CHANGE_THRESHOLD = 0.1  # |NDVI 2021 - NDVI 2001| above this is degradation / improvement
NDVI_CHANGE_LIMIT = 2.0  # outer bound of the reclassification table

# Codes of the final map.
OTHER = 0  # inside the study area, not forest in 2001 or not assessed
DEFORESTATION = 1  # forest in 2001, not forest in 2021
IMPROVED = 10  # stable forest, NDVI change > +0.1
STABLE = 20  # stable forest, NDVI change within +/-0.1
DEGRADED = 30  # stable forest, NDVI change < -0.1
NODATA = 255

CLASS_LABELS = {
    DEFORESTATION: "Deforestation",
    DEGRADED: "Degraded forest",
    STABLE: "Stable forest",
    IMPROVED: "Improved forest",
}
# Colours used in the GeoTIFF palette.
CLASS_COLOURS = {
    DEFORESTATION: "#1a1a1a",
    DEGRADED: "#e0360f",
    STABLE: "#e9ad07",
    IMPROVED: "#06a41f",
}
LAND_COLOUR = "#c6c6c6"

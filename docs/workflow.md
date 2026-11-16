# Methodology and reproducibility

## Input data and grid

- **Land cover.** 36 annual MCD12Q1 v6.1 tiles per year for 2001 and 2021, using the `LC_Type1` IGBP layer.
- **Surface reflectance.** 35 MOD09Q1 v6.1 tiles per composite, using band 1 (red) and band 2 (NIR). The analysis uses the 8-day composites starting on 28 July 2001 and 28 July 2021.
- **Grid.** South America Albers Equal Area Conic (ESRI:102033) at 500 m. The origin and dimensions are in the [run metadata](../results/run_metadata.json). The mosaics use nearest-neighbour sampling at the grid cell centres.
- **Boundaries.** GADM 4.1 level-0 polygons define the 13 reporting areas. The portfolio map is rendered separately using Natural Earth v5.1.1 map units for the same country and territory codes.

## Classification

NDVI is calculated per year as (NIR − red) / (NIR + red). A missing band or zero denominator yields an undefined NDVI. The analysis uses the two 8-day composites without a separate cloud or quality mask.

| Raster code | Condition |
| ---: | --- |
| 1 | IGBP classes 1–5 in 2001 and a non-forest class in 2021 |
| 10 | IGBP classes 1–5 in both years and ΔNDVI in (0.1, 2] |
| 20 | IGBP classes 1–5 in both years and ΔNDVI in [−0.1, 0.1] |
| 30 | IGBP classes 1–5 in both years and ΔNDVI in [−2, −0.1) |
| 0 | Other covered pixels, including areas classified as forest in 2021 only |
| 255 | Missing land cover, or forest in both years with an undefined or out-of-range ΔNDVI. Also used outside the study mask. |

ΔNDVI is NDVI 2021 minus NDVI 2001. Class 1 is determined by land cover independently of NDVI. Class changes are an educational analysis of MODIS labels. The [MCD12Q1 v6.1 user guide](https://lpdaac.usgs.gov/documents/1409/MCD12_User_Guide_V61.pdf) advises against treating those labels alone as a measure of real land-cover change.

## Areas and outputs

The zonal step counts pixels whose centres fall inside each reporting area. Each pixel covers 0.25 km². The [published CSV](../results/forest_change_by_country.csv) contains the `FIN_*` class counts and the areas in km². The GeoTIFF, GeoPackage and CSV counts were checked for agreement in the 142-tile run.

The output directory defaults to `data/output/`. It contains a thematic GeoTIFF, a GeoPackage and CSV with statistics by area, a separate table of land-cover transitions and the run metadata. The reporting polygons and generated GIS files stay local.

### Share of the 2001 forest area

The [land-cover transition counts](../results/forest_transitions_by_country.csv) supply both terms of the calculation. For each reporting area, the percentage is `100 × forest_loss_px / (forest_loss_px + stable_forest_px)`. The denominator counts the pixels classified as forest in 2001 with valid land-cover data in both years. The counts use land cover independently of NDVI. A reporting area without an eligible forest pixel has an undefined share.

## Verification

After generating local outputs, run:

```sh
uv run pytest
uv run forest-change check-boundaries
uv run forest-change compare
```

The boundary check compares the count of pixels inside each GADM polygon with the sum of class counts in the published table. The comparison reports the signed differences by class and territory between a local run and the published table. With the listed inputs and settings, both checks should report zero differences.

## Regenerate the figures

Both charts use the published CSV files. Regenerate them from the repository root:

```sh
uv run python scripts/plot_results.py
```

The map uses the MODIS tiles and the analysis classification before clipping to the Natural Earth mask. Its visual extent comes from Natural Earth and its legend describes the same MODIS classes. To regenerate the map alongside the charts, download the [Natural Earth 1:10m Admin 0 map units ZIP](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-details/) to `data/` and run:

```sh
uv run python scripts/plot_results.py --map-units data/ne_10m_admin_0_map_units.zip
```

## Alternative acquisitions

To test other 8-day MOD09Q1 composites, pass the first day of each composite:

```sh
uv run forest-change reproduce \
  --ndvi-start 2001-08-05 --ndvi-end 2021-08-05 \
  --results-dir data/august
uv run forest-change compare --candidate data/august/forest_change_by_country.csv
```

If you already have the HDF files, keep their filenames and place the annual tiles in `data/modis/MCD12Q1/A2001001/` and `data/modis/MCD12Q1/A2021001/`. Place the reflectance tiles in the corresponding `data/modis/MOD09Q1/AYYYYDDD/` folders, where `DDD` is the three-digit day of year. The `run` command uses these local inputs.

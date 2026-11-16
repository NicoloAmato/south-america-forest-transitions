"""Command-line interface for the forest change analysis."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import compare, config, earthdata, gadm, pipeline, zonal
from .grid import analysis_grid

REFERENCE = Path("results/forest_change_by_country.csv")
OUTPUT = Path("data/output")


def _parse_dates(args: argparse.Namespace) -> dict[int, str]:
    dates = {}
    for year, value in ((config.YEAR_START, args.ndvi_start), (config.YEAR_END, args.ndvi_end)):
        date = earthdata.composite_start(value)
        if date.year != year:
            raise ValueError(f"expected a composite in {year}, got {date}")
        dates[year] = date.isoformat()
    return dates


def _check_boundaries(data_dir: Path, reference_path: Path) -> None:
    countries = gadm.load_countries(pipeline.gadm_dir(data_dir))
    reference = pd.read_csv(reference_path).set_index("GID_0")
    if not reference.index.is_unique:
        raise ValueError("the reference table must contain at most one row per GADM code")
    zones = zonal.rasterize_zones(list(countries.geometry), analysis_grid())
    counts = np.zeros(len(countries) + 1, dtype=np.int64)
    for block in np.array_split(zones, 64):
        counts += np.bincount(block.ravel(), minlength=counts.size)
    report = pd.DataFrame({"grid_pixels": counts[1:]}, index=countries["GID_0"])
    report["reference_pixels"] = reference.loc[report.index, list(compare.PIXEL_COLUMNS)].sum(
        axis=1
    )
    report["difference_pixels"] = report["grid_pixels"] - report["reference_pixels"]
    report["difference_pct"] = 100 * report["difference_pixels"] / report["reference_pixels"]
    print(report.to_string(float_format=lambda value: f"{value:+.5f}"))


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    actions.add_parser("login", help="configure a local NASA Earthdata login")
    for command, help_text in (
        ("download", "download MODIS tiles and country boundaries"),
        ("run", "run the analysis from local inputs"),
        ("reproduce", "download inputs and run the analysis"),
    ):
        action = actions.add_parser(command, help=help_text)
        action.add_argument("--data-dir", type=Path, default=Path("data"))
        action.add_argument("--ndvi-start", default=config.NDVI_COMPOSITE_START[config.YEAR_START])
        action.add_argument("--ndvi-end", default=config.NDVI_COMPOSITE_START[config.YEAR_END])
        if command != "download":
            action.add_argument("--results-dir", type=Path, default=OUTPUT)
            action.add_argument("--workers", type=_positive_int, default=4)
            action.add_argument("--keep-intermediates", action="store_true")
    check = actions.add_parser(
        "check-boundaries", help="compare grid coverage with the published table"
    )
    check.add_argument("--data-dir", type=Path, default=Path("data"))
    check.add_argument("--reference", type=Path, default=REFERENCE)
    check.add_argument("--original", dest="reference", type=Path, help=argparse.SUPPRESS)
    comparison = actions.add_parser("compare", help="compare local and published counts")
    comparison.add_argument("--reference", type=Path, default=REFERENCE)
    comparison.add_argument("--original", dest="reference", type=Path, help=argparse.SUPPRESS)
    comparison.add_argument(
        "--candidate", type=Path, default=OUTPUT / "forest_change_by_country.csv"
    )
    comparison.add_argument("--reconstructed", dest="candidate", type=Path, help=argparse.SUPPRESS)
    comparison.add_argument("--output", type=Path, help="optionally save the differences as CSV")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("forestchange").setLevel(logging.INFO)

    try:
        if args.command == "login":
            earthdata.interactive_login()
        elif args.command == "check-boundaries":
            _check_boundaries(args.data_dir, args.reference)
        elif args.command == "compare":
            differences = compare.compare_tables(args.reference, args.candidate)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                differences.to_csv(args.output)
            else:
                print(differences.to_string())
        else:
            dates = _parse_dates(args)
            if args.command in ("download", "reproduce"):
                pipeline.download_inputs(args.data_dir, dates)
            if args.command in ("run", "reproduce"):
                pipeline.run(
                    args.data_dir,
                    args.results_dir,
                    dates,
                    keep_intermediates=args.keep_intermediates,
                    workers=args.workers,
                )
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"forest-change: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

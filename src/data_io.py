"""Loading and CRS harmonisation - the single entry point for every dataset.

Everything else in the kit assumes data arrives already in a known CRS. That
assumption is enforced here rather than hoped for, because the most expensive bug
in a geospatial hackathon is silent: a layer in the wrong CRS still plots, still
joins, and still produces a number. It is just the wrong number.

The working CRS is EPSG:3035 (ETRS89-LAEA), the European standard for anything
where area or distance matters. Not EPSG:4326: degrees are not metres, and a
buffer or an area computed in 4326 over Belgium is wrong by a factor that varies
with latitude.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import yaml

# Equal-area projection for Europe. Use it for every area, distance and zonal
# computation; convert to 4326 only at the last moment, for web maps.
WORKING_CRS = "EPSG:3035"
WEB_CRS = "EPSG:4326"

CONFIG = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
DATA = Path(__file__).resolve().parents[1] / "data"


def sources(section: str | None = None) -> dict | list:
    """The declared sources, from the one file that owns them.

    Read from `config/sources.yaml` rather than hard-coded anywhere, so that a URL
    change is a one-line edit and every number stays traceable to its provenance.
    """
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return data[section] if section else data


def load_vector(path: str | Path, crs: str = WORKING_CRS) -> gpd.GeoDataFrame:
    """Read a vector file and put it in the working CRS.

    Raises on a file with no CRS at all: guessing one is how a whole analysis
    silently lands in the wrong place.
    """
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(
            f"{path} declares no CRS. Find out what it is - do not assume 4326."
        )
    return gdf.to_crs(crs)


def to_web(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Convert to EPSG:4326 for folium/leaflet, as the last step before display."""
    return gdf.to_crs(WEB_CRS)


def check_alignment(gdf: gpd.GeoDataFrame, raster_crs: str) -> None:
    """Fail loudly when polygons and a raster disagree about where they are.

    Call this before any zonal statistic. `rasterstats` will happily return zeros
    for every polygon if the two are in different CRSs - a result that looks like
    "nobody is exposed" rather than like an error.
    """
    if gdf.crs is None:
        raise ValueError("The polygons have no CRS.")
    if str(gdf.crs).upper() != str(raster_crs).upper():
        raise ValueError(
            f"Polygons are in {gdf.crs} but the raster is in {raster_crs}. "
            "Reproject the polygons to the raster, not the other way round: "
            "reprojecting a raster of counts moves people between cells."
        )

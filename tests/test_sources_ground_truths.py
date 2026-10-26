"""Catalogue claims about the July 2021 ground truths, pinned to measured facts.

`config/sources.yaml` is where a reader learns what each observed layer covers,
so a wrong coverage claim there becomes a wrong validation claim in the brief.
Each test below pins one fact measured on the raw files and checks that the
catalogue entry states it, so a later edit cannot quietly restore the old claim
(EMSR517 AOI01 "is the Ahr", ALEA has only three classes per mechanism, the two
Walloon truths are interchangeable). Pure YAML reads: no raster, no network.
"""

from __future__ import annotations

import re

import pytest

from src import data_io


def _entries() -> dict[str, dict]:
    """Every declared source with an `id`, keyed by it, from all sections."""
    out: dict[str, dict] = {}
    for section in data_io.sources().values():
        if isinstance(section, list):
            for item in section:
                if isinstance(item, dict) and "id" in item:
                    out[item["id"]] = item
    return out


def _text(source_id: str) -> str:
    """The prose of one entry (purpose + caveat), whitespace-normalised."""
    entry = _entries()[source_id]
    prose = " ".join(str(entry.get(k, "")) for k in ("purpose", "caveat"))
    return re.sub(r"\s+", " ", prose)


def test_emsr517_aoi01_is_trier_mosel_not_the_ahr():
    """AOI01 is the Moselle around Trier (6.35-7.59 E, 49.54-50.37 N), with
    0.28 km2 observed; the Ahr is north of it, so the entry must say so."""
    text = _text("cems_emsr517_germany_2021")
    assert "Mosel" in text and "Trier" in text
    assert "0.28 km2" in text
    assert re.search(r"Ahr[^.]*(cannot|not) be validated", text)


def test_emsr517_keeps_its_single_declared_file():
    """The correction is prose only: the declared package and keys stay."""
    entry = _entries()["cems_emsr517_germany_2021"]
    assert entry["files"] == ["EMSR517_AOI01_DEL_PRODUCT_r1_VECTORS_v1_vector.zip"]
    assert {"id", "url", "landing", "access", "files", "purpose", "caveat",
            "verified"} <= set(entry)


def test_jrc_observed_depth_limits_the_cross_border_claim_to_belgium():
    """The footprint reaches the Ahr but only ~0.35 km2 is detected there."""
    text = _text("jrc_observed_flood_depth")
    assert "0.35 km2" in text
    assert re.search(r"limited to Belgium", text)


@pytest.mark.parametrize("code", ["101", "201", "301"])
def test_alea_declares_the_very_low_class(code):
    """CLASSEMENT x01 is 'Alea tres faible' in the raster's own .vat.dbf."""
    text = _text("wallonia_flood_hazard_official")
    assert code in text
    assert "tres faible" in text


def test_alea_says_an_any_class_mask_must_state_very_low():
    text = _text("wallonia_flood_hazard_official")
    assert re.search(r"any[- ]class", text, re.IGNORECASE)


def test_walloon_truths_state_their_areas_and_disagreement():
    """The depth raster and the extent gpkg are not the same footprint."""
    extent = _text("wallonia_observed_flooded_areas_2021")
    depth = _text("wallonia_observed_water_depth_2021")
    for text in (extent, depth):
        assert "77 km2" in text and "521 km2" in text
    assert "208,012" in extent and "17" in extent and "SCENARIO" in extent
    assert "Dyle" in extent and "Senne" in extent and "Gette" in extent

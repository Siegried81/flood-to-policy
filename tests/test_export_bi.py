"""Tests for the Power BI export, the semantic model that reads it, and the report.

The Power BI project is a third front end, so the failure to pin is a figure
that differs from the one the app and the brief quote. The export is checked
against the frozen tables, and the TMDL model against the export: a column
renamed on one side and not the other would load as an error in Power BI, far
from the change that caused it. The report is checked against the model and
against Microsoft's published PBIR schemas, because nobody opens Power BI
Desktop at every change and Desktop refuses a file that breaks its schema.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_bi_report, export_bi, validate_bi_report

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "bi" / "FloodToPolicy.SemanticModel" / "definition" / "tables"
REPORT = ROOT / "bi" / "FloodToPolicy.Report"

# The frozen tables are committed, so this skips only on a checkout that moved
# them aside - which is how the UI tests are checked for leaks - not in CI. The
# report tests read only the project files and never need it.
needs_frozen = pytest.mark.skipif(
    not (PROCESSED / "exposure.parquet").exists(),
    reason="the export is checked against the frozen exposure table",
)


def _frozen_exposure() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "exposure.parquet")


@needs_frozen
def test_the_eu27_headline_matches_the_frozen_table() -> None:
    """The number the brief opens with must come out of Power BI unchanged."""
    regions, exposure = export_bi.tables(PROCESSED)
    rp100 = exposure[exposure["return_period"] == 100].merge(
        regions[["nuts_id", "is_eu27"]], on="nuts_id"
    )
    frozen = _frozen_exposure()
    frozen_rp100 = frozen[(frozen["return_period"] == 100)
                          & frozen["country"].isin(export_bi.EU27)]
    assert len(export_bi.EU27) == 27
    assert rp100.loc[rp100["is_eu27"], "exposed_pop"].sum() == frozen_rp100["exposed_pop"].sum()


@needs_frozen
def test_one_region_row_per_region_and_every_scenario_row_kept() -> None:
    """A region duplicated in the dimension would double every figure joined to
    it; a scenario row dropped would silently lower one return period."""
    regions, exposure = export_bi.tables(PROCESSED)
    frozen = _frozen_exposure()
    assert regions["nuts_id"].is_unique
    assert set(regions["nuts_id"]) == set(frozen["nuts_id"])
    assert len(exposure) == len(frozen)


@needs_frozen
def test_list_cells_become_text_power_query_can_read() -> None:
    """Power Query reads a list cell as an error. The separator is "; " because
    a basin name can carry a comma ("Teno, Naatamo and Paatsjoki" split in two
    with ", "). The largest basin also gets a column of its own, so a slicer
    can filter on it."""
    regions, _ = export_bi.tables(PROCESSED)
    for column in ("shared_with", "shared_basins", "main_shared_basin"):
        assert regions[column].map(lambda v: isinstance(v, str)).all(), column
    named = regions[regions["shared_basins"] != ""]
    assert (named["shared_basins"].str.split("; ").str[0] == named["main_shared_basin"]).all()


def _tmdl_columns(name: str) -> list[str]:
    text = (TABLES / f"{name}.tmdl").read_text(encoding="utf-8")
    return re.findall(r"^\tcolumn (\S+)$", text, flags=re.M)


def _tmdl_typed_columns(name: str) -> list[str]:
    text = (TABLES / f"{name}.tmdl").read_text(encoding="utf-8")
    return re.findall(r'\{"([^"]+)", (?:type \w+|Int64\.Type)\}', text)


@needs_frozen
def test_the_model_declares_exactly_the_exported_columns() -> None:
    """Every TMDL column must exist in the CSV it reads, and every CSV column
    must be typed in the Power Query step - in the same order."""
    regions, exposure = export_bi.tables(PROCESSED)
    for name, frame in (("Regions", regions), ("Exposure", exposure)):
        assert _tmdl_columns(name) == list(frame.columns), name
        assert _tmdl_typed_columns(name) == list(frame.columns), name


def test_the_exposed_population_measure_refuses_a_sum_across_return_periods() -> None:
    """The extents are nested: the RP100 footprint contains the RP10 one, so a
    sum over return periods counts the same people several times. The measure
    must be blank unless one return period is selected."""
    text = (TABLES / "Exposure.tmdl").read_text(encoding="utf-8")
    measure = re.search(r"measure 'Exposed population' = (.+)", text).group(1)
    assert "HASONEVALUE(Exposure[return_period])" in measure
    summarize = re.search(r"column exposed_pop\n(?:\t\t.*\n)*?\t\tsummarizeBy: (\w+)", text)
    assert summarize.group(1) == "none", "a default sum would bypass the measure"


def test_topojson_keeps_every_region_and_its_join_key() -> None:
    """The Shape map joins on `nuts_id`; a dropped region is a grey hole."""
    geojson = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"nuts_id": "XX001", "name": "A"},
         "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        {"type": "Feature", "properties": {"nuts_id": "XX002", "name": "B"},
         "geometry": {"type": "MultiPolygon", "coordinates": [
             [[[2, 2], [3, 2], [3, 3], [2, 2]]], [[[4, 4], [5, 4], [5, 5], [4, 4]]]]}},
    ]}
    topology = export_bi.topojson(geojson)
    geometries = topology["objects"]["regions"]["geometries"]
    assert [g["properties"]["nuts_id"] for g in geometries] == ["XX001", "XX002"]
    assert geometries[1]["arcs"] == [[1], [2]]
    assert topology["arcs"][2] == [[4, 4], [5, 4], [5, 5], [4, 4]]


@needs_frozen
def test_main_writes_the_two_tables_and_skips_absent_geometry(tmp_path, monkeypatch, capsys) -> None:
    """A fresh clone has no regions.geojson: the tables are still written and the
    run says how to get the map."""
    processed = tmp_path / "processed"
    processed.mkdir()
    for name in ("exposure.parquet", "context.parquet"):
        shutil.copy(PROCESSED / name, processed / name)
    out = tmp_path / "bi"
    monkeypatch.setattr("sys.argv", ["export_bi.py", "--processed", str(processed), "--out", str(out)])
    assert export_bi.main() == 0
    assert (out / "regions.csv").exists() and (out / "exposure.csv").exists()
    assert not (out / "regions.topojson").exists()
    assert "build_geometry.py" in capsys.readouterr().out
    back = pd.read_csv(out / "exposure.csv")
    assert back["exposed_pop"].sum() == _frozen_exposure()["exposed_pop"].sum()


@needs_frozen
def test_a_layer_that_has_not_run_gives_empty_columns_not_missing_ones(tmp_path) -> None:
    """The HERA layer needs 69 GB of local files, so most checkouts lack it: its
    columns are still exported, empty, or Power Query fails on a declared
    column the CSV does not have."""
    processed = tmp_path / "processed"
    processed.mkdir()
    shutil.copy(PROCESSED / "exposure.parquet", processed / "exposure.parquet")
    context = pd.read_parquet(PROCESSED / "context.parquet")
    context.drop(columns=[c for c in context.columns if c.startswith("hera_")]).to_parquet(
        processed / "context.parquet")
    regions, _ = export_bi.tables(processed)
    hera = [c for c in export_bi.CONTEXT_COLUMNS if c.startswith("hera_")]
    assert len(hera) == 10 and set(hera) <= set(regions.columns)
    assert regions[hera].isna().all().all()


# --- the report (PBIR) -----------------------------------------------------------

def _report_files() -> list[Path]:
    return sorted((REPORT / "definition").rglob("*.json"))


def _visual(page: str, name: str) -> dict:
    path = REPORT / "definition" / "pages" / page / "visuals" / name / "visual.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _declared_fields() -> tuple[set, set]:
    """("Table.Field" for every column and measure, "Table.Hierarchy.Level" for every level)."""
    fields, levels = set(), set()
    for name in ("Regions", "Exposure"):
        text = (TABLES / f"{name}.tmdl").read_text(encoding="utf-8")
        fields |= {f"{name}.{c}" for c in re.findall(r"^\tcolumn (\S+)$", text, flags=re.M)}
        # Desktop drops the quotes around a one-word name on save (measure Population).
        fields |= {f"{name}.{a or b}" for a, b in re.findall(r"^\tmeasure (?:'([^']+)'|(\w+)) =", text, flags=re.M)}
        for hierarchy, body in re.findall(r"^\thierarchy (\S+)\n((?:\t\t.*\n|\n)*)", text, flags=re.M):
            levels |= {f"{name}.{hierarchy}.{lv}" for lv in re.findall(r"^\t\tlevel (\S+)$", body, flags=re.M)}
    return fields, levels


def _used_fields(node, aliases: dict | None = None):
    """Every field a PBIR file names: columns and measures as "Table.Field",
    hierarchy levels as "Table.Hierarchy.Level". A filter names its table
    through an alias declared in its `From`, so aliases are carried down."""
    aliases = dict(aliases or {})
    if isinstance(node, dict):
        for source in node.get("From", []):
            aliases[source["Name"]] = source["Entity"]
        for kind in ("Column", "Measure"):
            if isinstance(node.get(kind), dict) and "Property" in node[kind]:
                ref = node[kind]["Expression"]["SourceRef"]
                yield f"{ref.get('Entity') or aliases[ref['Source']]}.{node[kind]['Property']}"
        if "HierarchyLevel" in node:
            hierarchy = node["HierarchyLevel"]["Expression"]["Hierarchy"]
            ref = hierarchy["Expression"]["SourceRef"]
            yield (f"{ref.get('Entity') or aliases[ref['Source']]}."
                   f"{hierarchy['Hierarchy']}.{node['HierarchyLevel']['Level']}")
            return
        for value in node.values():
            yield from _used_fields(value, aliases)
    elif isinstance(node, list):
        for value in node:
            yield from _used_fields(value, aliases)


def test_every_field_the_report_shows_exists_in_the_model() -> None:
    """A visual bound to a renamed column or measure opens as a grey error box
    in Power BI, with nothing pointing back at the rename. Every field reference
    in every PBIR file counts - projections, sorts, filters, drillthrough
    bindings, colour rules - not only the visible ones."""
    fields, levels = _declared_fields()
    used = set()
    for path in _report_files():
        used |= set(_used_fields(json.loads(path.read_text(encoding="utf-8"))))
    assert "Exposure.Exposed population" in used, "the report has no data-bound visual"
    assert used <= fields | levels, sorted(used - fields - levels)


def test_the_legacy_layout_is_gone_and_the_project_opens_as_pbir() -> None:
    """definition.pbir version 1.0 allows only the legacy report.json layout;
    4.0 is the one that reads the definition folder."""
    assert not (REPORT / "report.json").exists()
    pbir = json.loads((REPORT / "definition.pbir").read_text(encoding="utf-8"))
    assert pbir["version"] == "4.0"
    assert pbir["datasetReference"] == {"byPath": {"path": "../FloodToPolicy.SemanticModel"}}


@pytest.mark.skipif(not validate_bi_report.THEME_SCHEMA.exists(), reason="schemas not vendored")
def test_every_project_json_file_validates_against_its_microsoft_schema() -> None:
    """Desktop blocks on a PBIR file that breaks its schema. The schemas are
    vendored in bi/schemas - microsoft/json-schemas and
    microsoft/powerbi-desktop-samples, both under the MIT licence, which
    permits copying them; the licence texts are kept beside them - so this
    runs offline. Each visual's formatting is also checked against the theme
    schema, because the visual schema accepts any formatting name."""
    files = validate_bi_report.project_files()
    assert sum(p.name == "visual.json" for p in files) > 40
    failures = {}
    for path in files:
        errors = validate_bi_report.validate_file(path)
        if path.name == "visual.json":
            errors += validate_bi_report.formatting_errors(path)
        if errors:
            failures[path.relative_to(ROOT).as_posix()] = errors
    assert not failures, failures


@pytest.mark.skipif(not validate_bi_report.THEME_SCHEMA.exists(), reason="schemas not vendored")
def test_the_validator_rejects_what_desktop_would_reject(tmp_path) -> None:
    """A validator that passes everything proves nothing: an unknown key, a
    misspelt formatting property, a bad enum value and a malformed colour rule
    must each be caught."""
    visual = _visual("where", "where_by_country")
    path = tmp_path / "visual.json"

    def errors(mutate) -> list:
        data = json.loads(json.dumps(visual))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")
        return validate_bi_report.validate_file(path) + validate_bi_report.formatting_errors(path)

    objects = lambda d: d["visual"]["objects"]  # noqa: E731
    assert errors(lambda d: None) == []
    assert errors(lambda d: d.update(bogus=1))
    assert errors(lambda d: objects(d)["labels"][0]["properties"].update(
        colour={"expr": {"Literal": {"Value": "'#000000'"}}}))
    assert errors(lambda d: objects(d)["categoryAxis"][0]["properties"].update(
        axisType={"expr": {"Literal": {"Value": "'Diagonal'"}}}))
    assert errors(lambda d: objects(d)["dataPoint"][0]["properties"]["fill"]["solid"]["color"]["expr"]
                  ["FillRule"].update(bogus=1))
    assert errors(lambda d: d["visual"]["query"]["sortDefinition"]["sort"][0].update(direction="Down"))


def test_regions_drill_down_from_country_to_region() -> None:
    """Drill-down needs a hierarchy on the category axis: the model declares
    Geography (Country, Region), and the Where page puts both levels on it."""
    _, levels = _declared_fields()
    assert {"Regions.Geography.Country", "Regions.Geography.Region"} <= levels
    category = _visual("where", "where_by_country")["visual"]["query"]["queryState"]["Category"]["projections"]
    assert [p["queryRef"] for p in category] == ["Regions.Geography.Country", "Regions.Geography.Region"]
    assert [p["active"] for p in category] == [True, False], "opens on countries, drills to regions"


def test_the_detail_pages_are_drillthroughs_bound_to_region_and_country() -> None:
    """Right-click a region or a country, then Drill through: the menu exists only
    if a page is bound as a drillthrough to a field the source visual carries, so
    the country bars need a page of their own on `country_name`, and each binding
    must point at that page's own drillthrough filter."""
    pages = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted((REPORT / "definition" / "pages").glob("*/page.json"))]
    drillthroughs = {p["name"]: p for p in pages if p.get("pageBinding", {}).get("type") == "Drillthrough"}
    bound_to = {}
    for name, page in drillthroughs.items():
        parameter, = page["pageBinding"]["parameters"]
        bound = {f["name"]: f for f in page["filterConfig"]["filters"]}[parameter["boundFilter"]]
        assert bound["howCreated"] == "Drillthrough"
        assert bound["field"] == parameter["fieldExpr"]
        column = parameter["fieldExpr"]["Column"]
        assert column["Expression"]["SourceRef"]["Entity"] == "Regions"
        assert f"Regions.{column['Property']}" in _declared_fields()[0]
        bound_to[name] = column["Property"]
        back = _visual(name, f"{name}_back")["visual"]["visualContainerObjects"]["visualLink"]
        assert back[0]["properties"]["type"]["expr"]["Literal"]["Value"] == "'Back'"
    assert bound_to == {"region_detail": "region", "country_detail": "country_name"}


def test_the_generator_still_writes_a_report_that_validates(tmp_path) -> None:
    """The committed report is what Power BI Desktop saved, not what the script
    writes: the owner edits it in Desktop, so byte-equality with the generator
    would fail on every save. What the generator still owes is a valid starting
    report with the same pages, should the project ever be bootstrapped again."""
    build_bi_report.build(tmp_path / "Report")
    rebuilt = sorted((tmp_path / "Report" / "definition").rglob("*.json"))
    failures = {p.name: e for p in rebuilt if (e := validate_bi_report.validate_file(p))}
    assert rebuilt and not failures, failures
    pages = {p.parent.name for p in rebuilt if p.name == "page.json"}
    assert pages == {p.parent.name for p in _report_files() if p.name == "page.json"}


def test_a_schema_desktop_writes_before_microsoft_publishes_it_is_read_as_the_last_published(tmp_path) -> None:
    """Desktop saves visualContainer 2.14.0 while 2.13.0 is the newest published
    schema. The file is checked against 2.13.0, which still rejects an unknown key."""
    visual = _visual("where", "where_by_country")
    visual["$schema"] = visual["$schema"].rsplit("/visualContainer/", 1)[0] + "/visualContainer/2.14.0/schema.json"
    path = tmp_path / "visual.json"
    path.write_text(json.dumps(visual), encoding="utf-8")
    assert validate_bi_report.validate_file(path) == []
    path.write_text(json.dumps({**visual, "bogus": 1}), encoding="utf-8")
    assert validate_bi_report.validate_file(path)


def test_every_page_laid_out_for_boundaries_credits_eurogeographics() -> None:
    """GISCO terms: a page that shows the region boundaries carries the credit.
    No page is required to: the committed report draws no map (a Shape map is
    added locally only, see docs/power_bi.md)."""
    for page in sorted((REPORT / "definition" / "pages").glob("*/")):
        texts = " ".join(p.read_text(encoding="utf-8") for p in page.rglob("visual.json"))
        if "regions.topojson" in texts or '"shapeMap"' in texts:
            assert "EuroGeographics for the administrative boundaries" in texts, page.name


def test_the_drill_down_is_visible_without_hovering() -> None:
    """The bar charts' drill arrows only appear on hover and were missed: the
    Where and Downstream pages carry a matrix whose rows are a hierarchy, with
    the +/- buttons switched on."""
    import json

    pages = ROOT / "bi" / "FloodToPolicy.Report" / "definition" / "pages"
    for page, visual in (("where", "where_regions"), ("downstream", "downstream_partners")):
        spec = json.loads((pages / page / "visuals" / visual / "visual.json").read_text(encoding="utf-8"))
        assert spec["visual"]["visualType"] == "pivotTable"
        assert len(spec["visual"]["query"]["queryState"]["Rows"]["projections"]) == 2
        row_headers = json.dumps(spec["visual"]["objects"]["rowHeaders"])
        assert "showExpandCollapseButtons" in row_headers


@needs_frozen
def test_the_residual_never_exceeds_the_undefended_figure() -> None:
    """Behind the defences can only be fewer people, never more: a residual above
    the undefended count would mean the two columns were joined on the wrong
    region or return period."""
    _, exposure = export_bi.tables(PROCESSED)
    paired = exposure.dropna(subset=["residual_exposed_pop", "exposed_pop"])
    if paired.empty:
        pytest.skip("no local residual run (exposure_protected.parquet) on this checkout")
    # Relative tolerance: the two runs sum the same cells in a different order, and
    # one Turkish row (TR832, RP75) reads 2e-5 more people out of 35,674.
    slack = 1e-9 * paired["exposed_pop"] + 1e-6
    assert (paired["residual_exposed_pop"] <= paired["exposed_pop"] + slack).all()


@needs_frozen
def test_a_fresh_clone_reads_the_residual_from_the_committed_context(tmp_path: Path) -> None:
    """Without the local residual run, the residual comes from context.parquet's
    residual_exposed_pop_rp* columns, so page 2 and the cover are not blank on a
    clone that has only the committed tables."""
    for name in ("exposure.parquet", "context.parquet"):
        shutil.copy(PROCESSED / name, tmp_path / name)
    _, exposure = export_bi.tables(tmp_path)
    context = pd.read_parquet(PROCESSED / "context.parquet").set_index("nuts_id")
    at_100 = exposure[exposure["return_period"] == 100].set_index("nuts_id")["residual_exposed_pop"]
    assert at_100.notna().any()
    pd.testing.assert_series_equal(
        at_100.dropna().sort_index(),
        context["residual_exposed_pop_rp100"].reindex(at_100.dropna().index).sort_index(),
        check_names=False,
    )


# --- navigation, tooltip and palette ----------------------------------------------

def _pages() -> dict:
    return {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
            for p in (REPORT / "definition" / "pages").glob("*/page.json")}


def _page_visuals(page: str) -> list:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((REPORT / "definition" / "pages" / page / "visuals").glob("*/visual.json"))]


def _links(visual: dict) -> dict:
    """The visualLink of a button as plain values: {"type": ..., "navigationSection": ...}."""
    props = visual["visual"].get("visualContainerObjects", {}).get("visualLink", [{}])[0].get("properties", {})
    return {k: v["expr"]["Literal"]["Value"].strip("'") for k, v in props.items()
            if "Literal" in v.get("expr", {})}


def _story_pages() -> list:
    """Pages a reader pages through: neither the drillthrough nor the tooltip."""
    return [name for name, page in _pages().items() if page.get("type") not in ("Drillthrough", "Tooltip")]


def test_the_report_opens_on_a_cover_that_links_to_every_story_page() -> None:
    """The cover states the findings and is the way in: it is the first page,
    and its tiles carry a page-navigation button to each chapter they quote."""
    order = json.loads((REPORT / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
    assert order["pageOrder"][0] == "overview" == order["activePageName"]
    tiles = [_links(v) for v in _page_visuals("overview")
             if v["visual"]["visualType"] == "actionButton" and "_tile" in v["name"]]
    assert len(tiles) == 6 and all(t["type"] == "PageNavigation" for t in tiles)
    assert {t["navigationSection"] for t in tiles} <= set(_story_pages())


def test_every_story_page_carries_the_same_navigation_bar() -> None:
    """One bar, one button per story page, on every story page, each pointing at
    a page that exists - a renamed page folder would otherwise leave a dead button."""
    story = _story_pages()
    assert len(story) <= 9, "a cover and eight story pages at most"
    for page in story:
        nav = [_links(v) for v in _page_visuals(page) if f"{page}_nav_" in v["name"]]
        assert [n["type"] for n in nav] == ["PageNavigation"] * len(story), page
        assert sorted(n["navigationSection"] for n in nav) == sorted(story), page


def test_the_tooltip_page_is_a_tooltip_and_the_charts_use_it() -> None:
    """A report-page tooltip needs a page of type Tooltip and, on each chart, a
    visualTooltip of type Canvas naming that page."""
    tooltips = [name for name, page in _pages().items() if page.get("type") == "Tooltip"]
    assert tooltips == [build_bi_report.TOOLTIP_PAGE]
    page = _pages()[tooltips[0]]
    assert page["pageBinding"]["type"] == "Tooltip" and page["visibility"] == "HiddenInViewMode"
    assert (page["width"], page["height"]) == (320, 240)
    wired = []
    for name in _story_pages():
        for v in _page_visuals(name):
            props = v["visual"]["visualContainerObjects"].get("visualTooltip", [{}])[0].get("properties", {})
            if props:
                assert props["type"]["expr"]["Literal"]["Value"] == "'Canvas'"
                assert props["section"]["expr"]["Literal"]["Value"] == f"'{tooltips[0]}'"
                wired.append(v["name"])
    assert {"where_by_country", "defences_by_country", "who_age", "declared_scatter"} <= set(wired)


def _hue_saturation(hex_: str) -> tuple[float, float]:
    import colorsys
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s


def test_no_orange_anywhere_in_the_theme_or_the_report() -> None:
    """The palette is BuPu with a sea-green accent: an orange (hue 15-50 degrees,
    clearly saturated) creeping back in from a default would break it."""
    files = _report_files() + [build_bi_report.THEME_PATH]
    found = {h for p in files for h in re.findall(r"#[0-9A-Fa-f]{6}\b", p.read_text(encoding="utf-8"))}
    assert found, "no colour found: the scan is not reading the files"
    orange = sorted(h for h in found if 15 <= _hue_saturation(h)[0] <= 50 and _hue_saturation(h)[1] > 0.35)
    assert not orange, orange


def test_every_page_but_the_tooltip_names_its_sources_and_credits_the_boundaries() -> None:
    for name in _pages():
        if name == build_bi_report.TOOLTIP_PAGE:
            continue
        source = [v for v in _page_visuals(name) if v["name"] == f"{name}_source"]
        assert source, name
        assert "EuroGeographics for the administrative boundaries" in json.dumps(source[0], ensure_ascii=False)


def test_no_field_shows_a_default_name() -> None:
    """A column or measure without a display name shows as "Sum of total_pop" or a
    raw measure name; every one the report shows is named for a reader. Only the
    hierarchy levels keep their own names (Country, Region)."""
    unnamed = []
    for path in _report_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for role, state in data.get("visual", {}).get("query", {}).get("queryState", {}).items():
            for p in state["projections"]:
                if "HierarchyLevel" not in p["field"] and not p.get("displayName"):
                    unnamed.append(f"{path.parent.name}:{role}:{p['queryRef']}")
    assert not unnamed, unnamed


@needs_frozen
def test_the_residual_annual_measure_is_the_trapezoid_of_the_regional_column() -> None:
    """`Residual expected annual exposure` writes the trapezoid of
    src/exposure.py as a weighted sum: each return period weighs half the gap
    between its neighbouring probabilities. Applied to the undefended headcount,
    those weights must give back the frozen Regions[expected_annual_exposure]."""
    regions, exposure = export_bi.tables(PROCESSED)
    probs = sorted(exposure["annual_probability"].unique())
    weight = {p: ((probs[min(i + 1, len(probs) - 1)] - probs[max(i - 1, 0)]) / 2) for i, p in enumerate(probs)}
    eu = exposure.merge(regions[["nuts_id", "is_eu27"]], on="nuts_id").query("is_eu27")
    weighted = (eu["exposed_pop"] * eu["annual_probability"].map(weight)).sum()
    assert weighted == pytest.approx(regions.loc[regions["is_eu27"], "expected_annual_exposure"].sum(), rel=1e-9)
    text = (TABLES / "Exposure.tmdl").read_text(encoding="utf-8")
    dax = re.search(r"measure 'Residual expected annual exposure' = (.+)", text).group(1)
    assert "ALL(Exposure[return_period], Exposure[annual_probability])" in dax
    assert "SUM(Exposure[residual_exposed_pop])" in dax


def test_every_button_switches_its_text_and_fill_on_outside_a_state():
    # A `show` only inside the default state left every navigation pill and
    # tile button blank in Desktop: the on/off flag is read from an entry
    # with no selector.
    visuals = [v for page in build_bi_report.PAGES for v in page()[1]]
    buttons = [v for v in visuals if v["visual"]["visualType"] == "actionButton"
               and "text" in v["visual"].get("objects", {})]
    assert buttons
    for v in buttons:
        for key in ("text", "fill"):
            entries = v["visual"]["objects"][key]
            assert any("selector" not in e and "show" in e["properties"] for e in entries), (v["name"], key)

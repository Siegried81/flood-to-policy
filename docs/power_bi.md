# Power BI: the same figures, for readers who work in Power BI

`bi/FloodToPolicy.pbip` is a Power BI project in text form (semantic model in TMDL,
report in PBIR: one JSON file per page and visual), so changes show up as diffs. Save it
as `.pbix` from Power BI Desktop to hand it on. It computes nothing of its own: every
number comes from `scripts/export_bi.py`, which reads the two frozen parquets with the
app's helpers, and `tests/test_export_bi.py` checks the EU-27 headline is unchanged and
that the model declares exactly the columns the export writes.

## Open it

1. Export the data (again after any rebuild of the frozen tables):
   `python scripts/export_bi.py` writes `bi/data/regions.csv`, `exposure.csv` and, when
   `data/processed/regions.geojson` exists, `regions.topojson`. `bi/data/` is not committed.
2. Open `bi/FloodToPolicy.pbip` in Power BI Desktop (a release that reads PBIR).
3. If the repository is not at `C:\flood-to-policy`: Transform data, Edit parameters,
   `DataFolder` = full path of `bi\data\` with a trailing backslash; then Refresh.

## The pages

A cover, eight story pages (headline, behind the defences, where, downstream of someone
else, what is at stake, who is exposed, declared vs exposed, rivers changing), two
drillthrough pages (region, country) and a tooltip page. Screenshots:
[`docs/screenshots/power_bi_*.png`](screenshots/). Every story page opens with a
navigation bar, a claim as its title and ends with a source line carrying the
EuroGeographics credit. Pages filter on EU-27 = True (clear it in the Filters pane for
all 37 countries). Page titles are static text: pick another return period and the cards
move, the title does not.

- **Return period**: one slicer synced across pages 1-4; none picked means 1-in-100.
- **Drill down**: bar charts sit on the `Regions[Geography]` hierarchy (country, region).
- **Drill through**: right-click a region or country, then Drill through. The target page
  ignores the source page's filters, so it shows all nine return periods. One name covers
  two regions (Jura: CH025 and FRC22) and the region card says so.
- **Navigation buttons** need Ctrl+click while editing in Desktop.

## The model

Two tables and one relationship (`Exposure[nuts_id]` to `Regions[nuts_id]`, many to one):
`Regions` (one row per NUTS3 region: names, country, `is_eu27`, population, over-65 share,
poverty rate, shared-basin and declared-area columns, climate and HERA columns) and
`Exposure` (one row per region and return period: `exposed_pop`, `hazard_coverage`,
`residual_exposed_pop`). Lists are joined with `"; "` because a basin name can contain a
comma.

The measures live on `Exposure`. The rules they enforce:

- **One return period at a time**: the selected one, RP100 when none is, blank when
  several are. Extents are nested, so a sum over periods counts people several times.
- **Expected annual exposure** is the trapezoid over RP10-RP500 only: a lower bound,
  never called an expected annual damage.
- **Share over 65 and poverty rate** are regional figures weighted by population, not the
  age or income of the exposed.
- **Declared share** is comparable within a country, not across; the median declared
  share is blank, not zero, for Ireland and Lithuania.
- **Climate**: medians and quartiles only; "agree" means the robust column (at least 80 %
  of members); "No data" where the layer has no value, never "No".
- **Residual** (behind the design standards): same one-period rule; a standard, not a
  guarantee. Hospitals and schools: RP100 only, blank where GISCO does not cover a country.
- Footprint and built-up shares are weighted by footprint area, never a mean of shares.

## Theme

`bi/FloodToPolicy.Report/StaticResources/RegisteredResources/FloodToPolicy.json`: light
grey page, white cards, Segoe UI, exposure in the ColorBrewer BuPu ramp (colourblind-safe),
one sea-green accent for cross-border figures, no orange (a test scans for it). If Desktop
opens the report without it, apply it by hand: View, Themes, Browse for themes.

## Map (optional, local)

Page 3 needs no map. For a local demo insert a Shape map (Location `Regions[nuts_id]`,
Color saturation `Share exposed`, custom map `bi/data/regions.topojson`). Never commit it:
the report would embed the TopoJSON and the boundaries are not committed (GISCO terms).
Prefer it to the Map visuals, which send data to Bing / Azure Maps.

## How the report is built and checked

- `scripts/build_bi_report.py` writes every PBIR file from one grid and palette; the
  report has since been saved in Desktop, so the saved files are the source and rerunning
  the script overwrites them (port a Desktop change into the script first).
- `scripts/validate_bi_report.py` checks each JSON file against the schema its `$schema`
  names, offline (schemas vendored in `bi/schemas/`, MIT). No schema checks the data roles
  a visual uses or how a page looks: those need Desktop.
- `tests/test_export_bi.py` also checks navigation, tooltip wiring, source lines and
  credits on every page, and that no field shows a default name.

## Before showing it

Credit "© EuroGeographics for the administrative boundaries" on every page; never show a
figure for "all return periods"; "Publish to web" is public, so share the `.pbix` instead.
On first open, check that the cover is first, the navigation bar jumps correctly, the
decomposition tree on page 4 renders and hovering a bar shows the "Tooltip: place" page.

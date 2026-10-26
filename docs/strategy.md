# What would actually win this

Written 2026-10-05 after verifying the sources live, with every figure re-measured
against them on 2026-10-06. The honest premise: on 29
October, sixty students will be given the same geospatial data. Most will produce
a risk map. The jury has seen a hundred risk maps.

## The find that changes the plan

**European Satellite-Derived Flood Depth Maps** — `jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/European_Satellite-Derived_Flood_Depth_Maps/`

| | |
|---|---|
| What | Flood depth from **observed** Sentinel-1 SAR, via FLEXTH + Copernicus GFM |
| Coverage | Europe, 2015-01-01 → 2025-12-31, no temporal gaps |
| Resolution | **20 m** — against the hazard maps' 3 arc-seconds, ~92 m north-south but ~60 m east-west at Belgian latitudes |
| Unit | **centimetres**, uint16, nodata 0, **9999 = permanent or seasonal water** |
| CRS | Equi7Grid Europe, user-defined — pass the proj4 string; the file names no code, though `pyproj` matches its WKT to EPSG:27704 |
| DOI | `10.2905/0bc96690-b89c-4909-9166-c2c322a20130` |

**The unit row is the whole finding's weak point.** This layer is in centimetres
and the hazard maps are in metres, so the comparison that makes the argument is
also the one place a factor-100 error would pass for a result. Convert, mask the
9999 water flag, and say in the brief which unit the published number is in. The
file names, the proj4 string and the July 2021 file (38 MB) are in
`config/sources.yaml`; `docs/datasets.md` has the rest.

This sits in the same FTP tree as the hazard maps most teams will use, one
directory across, and it is the difference between the two questions:

- *Where could water go?* — the modelled hazard maps. What everyone will use.
- *Where has water actually gone, for ten years?* — this. Almost nobody will find it.

It also retires the news idea entirely. Press coverage is a biased proxy for
flooding; a decade of satellite observation is not a proxy at all. `src/events.py`
stays as a last-resort recency check, but this is the real validation layer.

## The question most teams will not ask

The data supports a *comparison*, and a Commission audience acts on comparisons.
So the strongest framing is not "where is the risk" but **"where does the system
fail"**:

| Question | Why it is strong | What it needs |
|---|---|---|
| **Where does the model disagree with ten years of observation?** | The hazard maps model river flooding only, basins > 150 km². Regions that flooded on satellite but rank low on the model are the blind spot, named and mapped. A methods finding, which a scientific jury rewards more than a ranking. Belgium carries the calibration: two independent observations of July 2021 (EMSR518 and the Walloon layers) bound how much of the disagreement is the model and how much is the ground truth. | Satellite depth maps × hazard maps (convert cm → m first) |
| **What did the floods actually cost, where?** | The Risk Data Hub publishes observed economic loss, people affected and casualties per administrative unit and per event, 1983–2024 — so a modelled ranking can be scored against recorded consequence instead of being asserted. Verified live 2026-10-06. | Risk Data Hub, one `admin_unit_level` at a time |
| **Where is the protection gap widest?** | Exposure × (1 − insurance penetration). It is a live EU file (EIOPA), it is a real lever, and no student team will raise it. Your Solvay and banking background is the edge. | EIOPA dashboard + exposure |
| **Did the money go where the risk is?** | The EU Solidarity Fund publishes what it paid, to whom, after which disaster. Compare allocation against modelled risk. That is a finding about governance, not geography. | EUSF allocations + exposure |
| **Who is exposed in a basin they do not control?** | The Meuse rises in France, floods Belgium, reaches the Netherlands. A warning issued nationally arrives late downstream. This is an argument for EU-level action — exactly the conclusion this jury exists to hear. | River basin districts + NUTS3 |
| **Who is exposed but not counted?** | Undocumented residents, people in temporary housing, seasonal workers. The data gap *is* the finding, and it is the equality reading FARI's manifesto asks for. | Stated as a limitation, with named sources |
| **Which regions become a priority by 2050?** | Risk today is description. Risk moving is a decision. Regions crossing from "not a priority" to "priority" is a planning horizon a decision-maker can act on. | EURO-CORDEX / Copernicus CDS projections |

**If you pick one, pick the first.** It uses only data you already have, it needs
no extra credential, it produces a map nobody else will have, and its conclusion
is honest in a way juries notice: *we tested the tool we were given, and here is
where it is blind*.

## Sources that would strengthen it

Ranked by value per hour of work.

1. **Satellite flood depth maps** (above). Free, no key, same tree as the hazard
   maps. Declared in `sources.yaml` down to the single July 2021 file, 38 MB.
   **Download this week.**
2. **JRC Risk Data Hub** — no longer a plan, it is in the kit: `src/rdh.py`,
   called for real on 2026-10-06 (77 hazards, 1,297 Belgian loss rows, 1983–2024,
   the July 2021 event among them). It is the consequence layer, from the jury's
   own house. Two conditions attached: an EU Login token that dies after 10
   hours, and rows that are **nested by administrative level**, so every figure
   is computed at one declared `admin_unit_level` and quoted as the Hub's average
   across DFO, EM-DAT and HANZE. See `docs/datasets.md`.
3. **EM-DAT** — the international disaster database, run by CRED at **UCLouvain**.
   Deaths, damages and people affected per event. The Risk Data Hub already
   averages EM-DAT in, so this is now a cross-check on a number you can get
   without it rather than the only route to consequence — and citing a Belgian
   academic database to a Brussels jury does no harm. Free for non-commercial
   research, registration required — do it now, not on the day.
4. **EU Solidarity Fund allocations** — published, small, and nobody uses them.
   This is the governance question above.
5. **EIOPA protection gap dashboard** — the insurance angle, per country and
   peril.
6. **Copernicus Climate Data Store** (EURO-CORDEX) — the 2050 question. Heavier;
   only if you want the forward-looking framing.
7. **GDELT bulk files** — if you still want news, **do not use the API**: it
   rate-limits per IP and the penalty is sustained (measured: HTTP 429 through
   more than a minute of silence). The bulk export is a CSV every 15 minutes at
   `data.gdeltproject.org/gdeltv2/`, no key and no limit. Verified working.

## Stack

The current stack holds. Two additions worth the install:

- **DuckDB** — reads GDELT's 15-minute CSVs, and Parquet, with SQL and no server.
  If you touch the bulk files at all, this is how.
- **GeoParquet** (`gdf.to_parquet`) for every intermediate. It round-trips CRS and
  dtypes exactly, so a NUTS code never comes back as an integer with its leading
  zero gone — which would silently break every join.

What **not** to add: a vector database (a few thousand passages is one matrix
product), a tile server (the SVG choropleth works offline), or an agent framework
(the workflow is five fixed nodes and must stay inspectable).

## The out-of-the-box framing

Most teams will answer *"where is flood risk highest in Europe?"*

The answer that is different, defensible and squarely in this jury's values:

> **Risk of flooding is not the same as risk of being unprepared.**
> We mapped the second one.

Unpreparedness is composed of things you can actually measure:

- the model is **blind** there (satellite says flooded, hazard map says no),
- the people are **uninsured** there (protection gap),
- the money **did not arrive** there (Solidarity Fund),
- the warning comes from **another country** (cross-border basin),
- the population is **not in the data** at all.

Each component is sourced, each is a different lever, and each names a different
actor — which is exactly what a brief with three costed recommendations
needs. It also reframes the limitations section from an apology into the finding
itself, which is the move that distinguishes a student project from a piece of
science-for-policy.

And it answers the question the call actually asks — *how can AI be used
responsibly to help governments prepare* — rather than the question everyone will
answer, which is *where is the water*.

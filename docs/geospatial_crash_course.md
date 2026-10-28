# Geospatial crash course

This page has two readers and does not pretend otherwise.

The first is a teammate with no GIS background who has ten minutes before the
team starts working. For you, the **glossary** below is the whole page. Read it,
skip to **the one equation** and **return periods**, and you will follow every
conversation in the room and be able to challenge a number — which is the useful
thing, not knowing how to open a raster.

The second is whoever writes the code. For you, everything after the glossary is
a list of the specific ways this project's data will give you a wrong answer
without giving you an error. That is the distinguishing feature of geospatial
bugs: a layer in the wrong coordinate system still plots, still joins, still
produces a number. It is just the wrong number, and it looks plausible enough to
reach a slide.

`docs/datasets.md` is the catalogue — what each dataset is, its size, its
licence, its individual traps. This page is the concepts behind those traps, so
the two are meant to be read together and neither repeats the other.
`config/sources.yaml` is the single source of truth for both; where a figure here
disagrees with the YAML, the YAML is right.

## The ten-minute glossary

| Term | What it means | Why you care here |
|---|---|---|
| **Raster** | A grid of numbered cells, like a photo where every pixel holds a measurement instead of a colour | Flood depth and population both arrive as rasters |
| **Vector** | Points, lines and polygons with attributes — a region boundary, a hospital, a river | NUTS3 regions, communes, observed flood outlines |
| **CRS** | Coordinate reference system: the rule that turns a position on the round Earth into a pair of numbers on a flat grid | Five different ones in this project (four EPSG/ESRI codes plus Equi7Grid). This is where the afternoons go |
| **Reprojection** | Converting a layer from one CRS to another | Two layers must share a CRS before you can combine them at all |
| **Resolution** | How big one raster cell is on the ground | Hazard 3 arc-sec (~92 × 60 m), population 1 km, observed depth 20 m |
| **Nodata** | A sentinel value meaning "not measured here", not zero | −9999, −200, 0 and 9999 all appear. Summed as measurements they wreck a total |
| **Zonal statistic** | One number per polygon, computed from the raster cells inside it — a sum, a mean, a max | How "people exposed in Arr. Liège" is actually produced |
| **Return period** | The rarity label on a flood scenario. RP100 = a 1-in-100-years flood | Nine of them. They are scenarios, not forecasts, and they must never be added together |
| **Exposure** | Who and what is in the water | The first number the jury hears |
| **Vulnerability** | Who suffers most from the *same* water — age, income, isolation | The answer to "who needs help first", which is the policy question |
| **NUTS** | The EU's nested statistical regions: country → NUTS1 → NUTS2 → NUTS3 | NUTS3 (1,165 EU-27 regions; 1,345 polygons in the GISCO file) is this project's working unit |
| **IoU** | Intersection over Union: how much a predicted flood footprint overlaps a real one, from 0 (no overlap) to 1 (identical) | The credibility result — "we checked the model against what happened". `src/validate.py` computes it, and `validate.headline()` writes the sentence |

If you only remember two things: **a number without its unit and its CRS is not
a number**, and **nodata is not zero**.

## The one equation

```
Risk = Hazard × Exposure × Vulnerability
```

In plain words, and in the order the analysis builds it:

- **Hazard** is a property of the water. Where does it go, and how deep, for a
  given scenario? Nobody is in the picture yet. This is the JRC flood hazard
  raster.
- **Exposure** puts people in the picture. How many residents live in the cells
  the water reaches? This is hazard × the GHS-POP population grid, summed per
  region, and it is what `src/exposure.py` computes.
- **Vulnerability** asks who those people are. An 85-year-old on a ground floor
  without a car is not in the same situation as a 30-year-old on the second
  floor, though the water over both is identical. This is `src/vulnerability.py`.

The multiplication is conceptual, not literal arithmetic — the three are measured
in incompatible units and the code never actually multiplies them together. What
it means is that **all three have to be non-zero for there to be risk**. Deep
water over an empty moor is a hazard and not a risk. A dense, poor, elderly
neighbourhood on a hill is vulnerable and not at risk.

The practical consequence is where an analysis stops. Stopping at exposure
answers *how many people got wet*. Reaching vulnerability answers *who needs help
first*, and only the second is a thing a decision-maker can act on.

## Return period: what "a 100-year flood" is not

This will be in the brief and a jury will ask about it, so get it right out loud.

RP100 does **not** mean the flood happens every hundred years, and it does not
mean that having had one you are safe for a century. It means that in any given
year there is a **1-in-100 chance** of a flood at least that large — an annual
exceedance probability of 1%. `src/exposure.py` attaches exactly this inversion
to every row as `annual_probability = 1 / return_period`, so nobody has to
remember it downstream.

Two things follow, and both are rhetorically useful:

**Rare does not mean distant.** Over a 30-year mortgage, the chance of seeing at
least one RP100 flood is `1 − 0.99³⁰ ≈ 26%`. "A one-in-a-hundred-year event" and
"roughly a one-in-four chance during the time you own the house" are the same
statement, and the second is the one that moves a decision-maker.

**Two in a decade is not evidence the model is broken.** Independent 1% events
cluster; that is what randomness does. Saying this before someone else does is
worth more than defending the model afterwards.

The third thing is a bug rather than a talking point. **Return-period extents are
nested**: the RP100 flood zone contains the RP10 zone, which contains nothing
smaller still. So the nine return periods are nine views of the same floodplain
and **must never be summed** — adding RP10 + RP100 + RP500 triple-counts the core
floodplain and produces a number larger than the population of the region.
Report each separately, or integrate across probability with
`exposure.expected_annual_exposure`, which is the probability-weighted version
and the entry point to any cost-benefit argument. The nesting is the intent of
the maps, not a property of every cell: each JRC raster is its own model run,
and four regions count fewer people at a rarer period (see
[`limitations.md`](limitations.md)). Never sum them, and never promise the figure
only grows.

One honesty note that belongs next to every return period in this kit: the JRC
maps model **river flooding only**, in basins larger than 150 km². The surface
runoff that destroyed much of the Vesdre valley in 2021 is not in them at all.
An RP100 map is not "the worst case" — it is one mechanism's hundred-year case.

## What a CRS is, and why there are four of them here

The Earth is round and a screen, a GeoTIFF and `shapely` are flat. A CRS is the
agreed recipe for flattening: which model of the Earth's shape, which projection,
which origin, and what the two numbers mean once you have them. Give two layers
different recipes and they describe the same place with different numbers.

The single most important consequence: **in EPSG:4326 the coordinates are degrees
of latitude and longitude, and a degree is not a length.** A degree of latitude
is about 111 km everywhere, but a degree of longitude is 111 km at the equator
and shrinks to zero at the pole. So in 4326, `geometry.area` returns square
degrees — a quantity with no physical meaning that varies with latitude — and
a 5 km buffer is not 5 km. The failure mode is the usual one: it does not raise,
it returns a number. Pan-European totals built this way are systematically wrong
in a way that depends on which countries are in them.

That is why this repo fixes a working CRS and enforces it in one place:

```python
WORKING_CRS = "EPSG:3035"   # ETRS89-LAEA: equal-area, metres, Europe
WEB_CRS     = "EPSG:4326"   # degrees — display only, and only at the last step
```

**EPSG:3035 for every area, distance, buffer and zonal computation. EPSG:4326
only at the final step, for a web map.** `data_io.load_vector()` reprojects on
read and refuses a file that declares no CRS at all, because guessing one is how
a whole analysis silently lands in the wrong place. `data_io.to_web()` is the
conversion back out, and it is meant to be the last thing that happens before
display.

The four CRSs you will actually meet, and what each one demands:

| CRS | Which data | What it needs from you |
|---|---|---|
| **EPSG:3035** ETRS89-LAEA | GISCO NUTS3 and LAU; the working CRS | Nothing. This is home |
| **EPSG:4326** WGS84 | The JRC hazard rasters, 3 arc-sec | Never compute an area or a distance in it. See the next section |
| **ESRI:54009** World Mollweide | GHS-POP population grids | **`EPSG:54009` is not a valid code.** The file carries only an ESRI WKT string ("World_Mollweide", which pyproj resolves to ESRI:54009). Pass the WKT, or `+proj=moll +lon_0=0 +datum=WGS84 +units=m` |
| **EPSG:31370** Belgian Lambert 72 | The Walloon *aléa* and July 2021 layers | Reproject before joining to anything European. Belgium-only, so this one appears in the Belgian validation of July 2021 |

And a fifth that is not an EPSG code at all. The satellite-derived observed depth
maps are on **Equi7Grid Europe**, an azimuthal equidistant grid declared
user-defined in the file (`ProjectedCSTypeGeoKey 32767`) with only an ESRI
citation string. The file names no EPSG code for it - its own
`ProjCenterLong` is 24.0 and `ProjCenterLat` 53.0 — the right way round, checked. pyproj and rasterio do match its WKT to EPSG:27704
("WGS 84 / Equi7 Europe"), but that is a lookup, not what the file declares. You
have to hand the proj4 string over yourself:

```
+proj=aeqd +lat_0=53 +lon_0=24 +x_0=5837287.81977 +y_0=2121415.69617
+datum=WGS84 +units=m
```

This matters more than it looks, because this is the **validation layer** — the
layer the whole credibility result is scored against. A CRS mistake here does not
produce a wrong total, it produces a comparison between two places.

## Non-square cells: the most expensive beginner bug here

The hazard rasters are 3 arc-seconds — `0.000833333°` — in EPSG:4326. One cell is
therefore **about 92 m north–south but only about 60 m east–west at Belgian
latitudes**, because the degree of longitude has shrunk and the degree of
latitude has not.

Every naive area calculation on these files is wrong, and wrong differently along
each axis. `cell_count × 92 × 92` overstates; `cell_count × 60 × 60` understates;
`cell_count × some_constant` is wrong by a factor that changes as you move from
Sicily to Finland, which is precisely the comparison a European brief is built
on. There is no constant that fixes it, because the cells are not the same size
in different places.

The fix is not a correction factor, it is the working CRS. **Reproject to
EPSG:3035, where cells are square metres by construction, and then measure.**
Equal-area is the whole point of ETRS89-LAEA and the reason it is the European
standard for this kind of work.

A related trap from the same family: the much-quoted "100 m, ETRS89-LAEA"
description of the JRC hazard maps belongs to the **retired v2.x**. The current
v3.1.1 files are 3 arc-sec in 4326. Build a pipeline on the literature's figure
and everything misaligns.

## Units: the factor-100 that returns a plausible number

Two depth layers in this project, two different units:

| Layer | Unit | Type | Nodata | And also |
|---|---|---|---|---|
| JRC hazard maps | **metres** | Float32 | −9999 | `Europe_spurious_depth_areas.tif` flags predicted depths > 10 m in small channels — mask or flag them |
| Satellite-derived observed depth | **centimetres** | uint16 | 0 | **9999 means permanent or seasonal water**, not a 99 m flood |

Comparing a modelled depth in metres against an observed depth in centimetres is
a factor-100 error, and it is the most dangerous mistake available in this kit
for one reason: **it does not crash.** It returns a number, in the right shape,
with the right region codes attached, that is wrong by two orders of magnitude.
A model under-predicting by 100× looks like a devastating finding about the
model. It is a finding about your arithmetic.

The cheap defence is to look at the range before trusting anything. A river
hazard map tops out at a handful of metres. The observed map tops out in the
thousands of centimetres plus the 9999 flag. If a depth histogram runs to 900,
you are in centimetres whatever you believed.

And **9999 is not a measurement.** Leave it in and a stretch of the Meuse becomes
the deepest flood in European history, which will drag the regional mean with it.
Mask it exactly as you mask `nodata 0`.

## Counts versus densities, and which layer gets reprojected

GHS-POP cells hold **residents per cell** — a count of people, not a density.
That single fact decides three things:

- **Counts are summable.** The sum over the cells in a region is the population
  of the region. That is the correct operation.
- **Counts must never be averaged.** The mean of a population grid is "the
  average number of people per 1 km cell", which is not a quantity anyone wants.
- **Counts must never be multiplied by cell area.** That is the operation for a
  *density* layer (people per km²). Apply it to a count layer and you multiply
  the population of Europe by a million.

Nodata is **−200**. Summed as a measurement it quietly removes two hundred people
per unmeasured cell, so it has to be masked; `src/exposure.py` reads with
`masked=True` then `filled(0)`, on the reasoning that an unmeasured population
cell is zero people for an exposure total, not an unknown that should poison the
sum into NaN.

The same fact also settles which of two misaligned rasters gets moved.
**Reproject the hazard onto the population grid, never the population onto the
hazard.** Resampling a grid of counts redistributes people between cells and
invents or destroys population in the process; resampling a depth or a wet/dry
mask does not — it is just a different reading of the same surface.

Which leaves the question of how a 1 km population cell that is *partly* flooded
should count. At 1 km with a 3 arc-sec hazard input there are roughly **185
hazard cells inside each population cell** at Belgian latitudes — not a constant:
the cell keeps its ~92.7 m north-south height everywhere, but its east-west width
is 111,320 m × cos(latitude) / 1,200, so 51°N gives ~58 m, a ~5,420 m² cell and
185 per km², while 35°N gives ~142 per km² and 65°N ~274. Say "well over a
hundred" rather than quoting one figure as if it held across Europe. Either way
the share flooded is well resolved — better than a percent even in the coarsest
European case — which is what lets
`exposure.exposed_population(mode="fraction")` use it:

1. Threshold the hazard into a 0/1 wet mask **at the hazard's own resolution**.
2. Resample that mask onto the population grid with `average` — the average of a
   0/1 mask *is* the fraction of the cell that is flooded, a number in [0, 1].
3. `exposed = population × fraction_flooded`.
4. Zonal-sum per region.

**The order in step 1 and 2 is load-bearing.** Averaging the depths first and
thresholding afterwards answers a different question — *is the mean depth over
this square kilometre above the threshold?* — and systematically under-reports
small deep floods, which are exactly the events that kill people in narrow
valleys. The alternative `mode="binary"` takes a `max` instead, counting a cell
as fully flooded if any part of it is; it never loads a continental raster into
memory, which is why it exists, but at 1 km it over-estimates badly.

One nodata trap in that reprojection is worth knowing because the symptom is
spectacular: the destination nodata must be **NaN, not 0**. With `dst_nodata=0`,
GDAL refuses to let a genuine depth of 0 collide with the sentinel and silently
rewrites it to `1.4e-45` — a positive number, so a later `> 0` test matches every
dry cell and **the entire study area reads as flooded**. `NaN` cannot collide
with a depth, and `NaN > threshold` is `False`, which is the reading you want.

## Zonal statistics, and the alignment that has to come first

A zonal statistic is one number per polygon, computed from the raster cells
falling inside it: *sum the population cells inside Arr. Liège*, *take the mean
depth inside this commune*. It is the operation that turns two rasters into a
table a brief can print, and almost every number in this project is one.

**Both layers must be in the same CRS before you start.** `rasterstats` reads the
array as-is and uses only its affine transform; it has no idea the polygons live
somewhere else. Hand it a mismatched pair and it does not raise — it returns
**zero for every polygon**, which reads as "nobody is exposed" rather than as an
error, and "nobody is exposed" is a publishable-looking result. That is what
`data_io.check_alignment(gdf, raster_crs)` is for: call it before any zonal
statistic and the mismatch becomes an exception instead of a finding. Nothing in
the pipeline calls it today; `build_exposure.py` asserts the CRS itself.

Note which way it tells you to fix the mismatch — **reproject the polygons to the
raster**, for the reason in the previous section.

Then choose the statistic, because the choice changes what the number *means*:

- **Sum, for population.** The cells are counts; their sum is the number of
  people. This is the only defensible choice for exposure.
- **Mean, for depth**, when the question is "how bad is it here on average".
  Beware what the denominator includes: a mean over the whole region mixes dry
  cells in and drags the answer towards zero, so a mean depth is only meaningful
  over the *flooded* cells, and you have to say which you did.
- **Max, for depth**, when the question is "could anywhere here be dangerous".
  Conservative by construction, and it answers a question about the worst cell
  rather than about the region — perfectly legitimate, and not comparable to a
  mean.

A region with a 2 m maximum and a 4 cm mean is a region with one flooded street.
A region with a 30 cm mean everywhere is a different policy problem. Reporting
one and calling it "depth" hides which situation you are in.

Two mechanics that bite:

**`all_touched`.** With `all_touched=False` (the default here) a cell belongs to
the unit containing its centre, so the per-unit sums add up to the national
total. With `True` every boundary cell is counted in *both* neighbours and the
sum over all units exceeds the total. Use `True` only for "does this unit touch
the flood zone at all?" questions, never for a total.

**Cells are all-or-nothing.** `zonal_stats` counts a cell as wholly in or wholly
out of a polygon, so the induced error scales with perimeter over area: around
**1–3% for a commune** (~5,000 cells) but **30–50% for a Belgian statistical
sector** (tens of cells). At NUTS3 it is negligible. If the scenario on the day
asks for anything smaller than a commune, switch to `exactextract`, which weights
each cell by the fraction actually covered.

And one distinction to keep: `count == 0` means the polygon overlapped no cell at
all — off the edge of the raster, or smaller than one cell. That is **not
measured**, and it is not the same as a measured zero. `exposed_population` keeps
it missing rather than reporting 0.0, because the difference decides whether a
region belongs in the brief at all.

## NUTS levels, and the nesting trap

NUTS is the EU's nested statistical geography, and the nesting is literal — the
codes are prefixes of each other. The Belgian chain, all the way down:

| Level | Code | Name |
|---|---|---|
| Country | `BE` | Belgium |
| NUTS1 | `BE3` | Région wallonne |
| NUTS2 | `BE33` | Prov. Liège |
| NUTS3 | `BE332` | Arr. Liège |

`BE332` is one arrondissement of about 637,220 people (Eurostat `demo_r_pjangrp3`,
checked live). The EU-27 has **1,165 NUTS3 regions** on the NUTS 2024
vintage this kit pins (the GISCO file also carries EFTA and the candidate
countries, 1,345 polygons in all), and
that is this project's working unit: fine enough to rank and map meaningfully,
coarse enough that a pan-European run finishes in minutes, and the level EU
regional policy actually operates on — a JRC jury thinks in NUTS. See
`docs/scope.md` for why. LAU (communes: 95,066 in the EU-27, 97,987 in the whole
GISCO LAU 2024 file) is for a zoom-in on one named valley and nothing else.

**The trap: a statistics table published at several levels at once cannot be
summed.** Because the levels nest, the same event appears once as `BE`, once as
`BE3`, once as `BE33` and once as `BE332` — the same casualties, four times. Add
every row and you count each person once per level.

This is not hypothetical, it is measured on the Risk Data Hub's casualty rows for
the July 2021 flood:

```
sum of every row                  = 114.01   <- four levels added together
sum at Country only  (1 unit)     =  29.67
sum at NUTS1 only    (2 units)    =  29.67
sum at NUTS2 only    (6 units)    =  29.67   <- the hierarchy is coherent
sum at NUTS3 only   (16 units)    =  25.00
```

Those middle three lines are the reassuring part: the hierarchy is internally
consistent, so *any one level* gives the same answer. The first line is a
wrong number nearly four times too large that arrives with no warning at all.
**Filter to one level, say which, and do the arithmetic there.** In
`src/losses.py` the level is a required argument of `select_level`, which is the
only function that creates a summable value column — so an unlevelled sum is not
expressible rather than merely discouraged.

The last line is a second, subtler fact: **NUTS3 is incomplete here by about
16%**. Roughly one casualty in six is not attributed to an arrondissement, so a
NUTS3 total is a *lower bound* and the brief has to say so. Nothing in this repo
redistributes the gap — inventing an allocation would be a claim about where
people died — so every per-unit total carries its coverage ratio instead.

**And pin the vintage.** NUTS 2021 and NUTS 2024 are different geometries *and*
different code sets. A boundary file with no year in its name is a trap, and two
tables on different vintages join partially and silently. Check for unmatched
codes after every merge rather than assuming the vintages agree.

## Vintage mismatches: 581 communes against 565

The same problem one level down, and worth its own section because it is the
join most likely to be attempted on the day.

GISCO LAU 2024 has **581** Belgian communes. The Statbel 2026 population file has
**565**. Neither is wrong: Belgian mergers took effect **2025-01-01**, and GISCO
publishes no LAU for 2025 or later. The Statbel income file is on the old 581
geography as well, because its latest fiscal year is 2023.

A plain join on the commune key will match most rows, drop the renamed ones, and
leave a national total that still looks entirely reasonable — which is why this
is dangerous rather than merely annoying. **Pick one vintage, build the
crosswalk, and check the row count after the join.** For current geometry,
Statbel's own statistical sectors are the alternative. `docs/datasets.md` has the
file-level detail.

The general rule, since this will recur with every dataset pairing: an
administrative boundary is a *dated* object. Two files that both say "Belgium"
are not the same Belgium unless they say the same year.

## Scoring a prediction against reality: IoU, hit rate, false alarm ratio

The credibility result is a comparison: the modelled hazard map says the
water goes *here*, the July 2021 observations say it went *there*, so how close
was the model? "We checked" is worth more to a scientific jury than any ranking,
and it needs a number. `src/validate.py` is where that number is produced — the
API is at the end of this section; what follows first is what the number means,
because the code cannot tell you which of the three to quote.

Put both extents on the same grid, in the same CRS, and classify every cell:

|  | observed wet | observed dry |
|---|---|---|
| **predicted wet** | hit | false alarm |
| **predicted dry** | miss | correct dry |

Three scores come out of that, and they answer different questions:

```
IoU (Jaccard, a.k.a. Critical Success Index) = hits / (hits + misses + false alarms)
Hit rate (probability of detection)          = hits / (hits + misses)
False alarm ratio                            = false alarms / (hits + false alarms)
```

- **IoU** is overlap over combined footprint: 1 is a perfect match, 0 is no
  overlap at all. It is the single headline number.
- **Hit rate** is how much of the real flood the model found.
- **False alarm ratio** is how much of the model's flood was not real.

**Report at least two of the three.** Hit rate alone is gameable to the point of
meaninglessness: a map that declares all of Belgium flooded scores a perfect hit
rate of 1.0. It is the false alarm ratio that catches it, and IoU that balances
them. Note also what is *not* in any of these formulas — the "correct dry" cell
count. It is excluded deliberately, because dry land dominates any flood map, so
a plain accuracy figure comes out at 99%-something for a model that found nothing.
If someone quotes accuracy on a flood extent, that is the error.

Three decisions have to be stated before the number means anything, because each
one moves it:

1. **What counts as wet in the model.** Any water at all, or above a damage
   threshold? `exposed_population`'s `min_depth_m` is the same knob: 0.0 is "any
   water", 0.5 m is the usual threshold for building damage, and the difference
   changes the headline without any change of data.
2. **What counts as wet in the observation**, after masking the 9999
   permanent-water flag — and in centimetres, not metres. The declared nodata 0
   is *not* masked when scoring: it means "dry or unseen", and dropping it would
   empty the false alarm ratio's denominator (`score_event` reads the layer with
   `OBSERVED_READ_NODATA` for that reason).
3. **Which grid you scored on.** The observed maps are 20 m, the hazard maps
   ~92 × 60 m. Whoever gets resampled onto whom, and with what rule, is part of
   the result.

And the honest framing to carry into the brief: **the ground truth has its own
uncertainty.** Belgium has two independent observations of the July 2021 flood —
Copernicus EMSR518 and the Walloon administration's own layers. Scoring those two
against *each other* first gives the spread of the observation itself, which is
what turns "the model misses X%" into a defensible number rather than an artefact
of one delineation. Sentinel-1 also sees extent under cloud but not under dense
canopy or in narrow urban streets, and a revisit gap can miss a flash flood that
drained in hours — so an *absence* in the observed layer is weaker evidence than
a presence.

`src/validate.py` computes all three, and 54 tests in `tests/test_validate.py`
cover them. The arithmetic really is a few lines over two aligned boolean arrays;
the alignment is the part that takes the time, which is why the module is shaped
the way it is:

- `agreement(modelled_flooded, observed_flooded, scorable=...)` returns an
  `Agreement` — the four confusion-matrix counts, the three scores, both depth
  thresholds and the caveat, all on one frozen record.
- `agreement_by_unit(..., unit_codes)` gives the same breakdown per NUTS3 region
  or per commune, as a DataFrame.
- `headline(scores, return_period_years=100)` turns one `Agreement` into the
  sentence the brief quotes, and says *could not be measured* rather than 0%
  when the hit rate is undefined.
- `score_event(modelled_path, observed_path)` is the one-call path from two
  files: `scoring_grid` builds the shared grid first — EPSG:3035 at 20 m, the
  intersection of both footprints, nearest neighbour — so there is no argument
  order that compares EPSG:4326 cells against Equi7Grid ones.

Three habits of that module are worth copying rather than re-deriving. **A ratio
with an empty denominator is `None`, never `0.0`** (NaN in the per-unit frame):
"we could not measure" and "the score is zero" are different statements, and only
the second is a finding. **The two depth thresholds are derived from one
another** by `matching_threshold_cm()`, so the metres value cannot reach the
centimetre raster — that is the factor-100 error, and it returns a believable
percentage. **The runoff split is reported, not buried:** pass `runoff` to
`agreement_by_unit` (from
`runoff_mask_from_classement`, over the Walloon `CLASSEMENT` 2xx/3xx codes) and
you also get `hit_rate_outside_runoff_area`, the score over the flooding the
hazard maps actually claim to cover. A unit with a poor overall hit rate and a
good outside-runoff one is a finding about scope, not about accuracy.

The scoring arithmetic is pure numpy and runs anywhere. The raster reading
imports rasterio inside the three functions that need it, so on a machine whose
policy blocks the GDAL DLLs, `import src.validate` and the 54 tests still work
and only the IO half needs WSL or the container. On this machine rasterio does
load — what the application-control policy refuses is pyogrio 0.13 and pyproj 3.8,
which is why `requirements.txt` caps both.

## First five things to check when a number looks wrong

In this order. The first two catch most of it.

1. **Is everything in the same CRS?** Print `gdf.crs` and `src.crs` and compare
   them with your eyes. `None` is not 4326 — it means the file declares nothing
   and something downstream is about to assume. If a zonal statistic came back as
   zero for *every* polygon, stop here: that is the mismatch signature, and
   `check_alignment` would have said so.
2. **Are the units what you think?** Print `a.min(), a.max()` on the band. Depth
   in metres tops out in single digits; depth in centimetres runs to the
   hundreds. A total that is out by almost exactly 100 or 10,000 is a unit bug,
   not a model finding.
3. **Is a nodata sentinel being summed as a measurement?** Print `src.nodata`.
   `None` is a red flag — find out what the file actually uses (−9999, −200, 0
   and 9999 all appear in this project) and declare it yourself. A population
   total that is implausibly low, or a mean depth that is negative, is usually
   −9999 or −200 inside the sum.
4. **Did you average something that should have been summed, or sum something
   that should have been averaged?** Population cells are counts: sum them, never
   average them, never multiply them by cell area. Depths are measurements: a
   mean or a max, and which one changes the meaning. And check the denominator of
   any mean — over all cells, or only the wet ones?
5. **Are you double counting?** Two ways in this project. Nested admin levels:
   a loss table filtered to no single `admin_unit_level` sums each event about
   four times over. Nested return periods: RP10 ⊂ RP100 ⊂ RP500, so adding them
   triple-counts the core floodplain. Both produce a total that is too large by a
   suspiciously round-ish factor.

If all five pass and the number is still strange, compare a total against a
published figure for the same area — the population of a NUTS3 region is public,
and a population grid that sums to twice it is telling you something before you
have to debug anything else.

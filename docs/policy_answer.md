# The answer: what we found, who has to act

Figures are re-derived from `data/processed/event_2021_*.parquet`, `exposure.parquet`,
`context.parquet`, the cached APSFR layer and the Floods Directive text in
`data/raw/scrape/`. Re-derive them rather than quoting this page; the tables are rebuilt
and the counts move. This page records what the kit supports and names the authority
behind each recommendation; sources are declared in `config/sources.yaml`.

**In one sentence.** AI can help if every figure carries its limits: in July 2021 the
water reached people the European map didn't cover (91 % in Eschweiler), about 25.7
million EU-27 residents live in the 1-in-100-year zone, and three reporting fixes before
the 22 Dec 2027 review would make the next warning comparable across borders. The AI
part here drafts the brief from the table and the law, checks every figure and citation
offline, and stops until a person approves.

**The question.** Can AI help Europe anticipate flood risk, and how can it be used
responsibly to help governments prepare? The core is the July 2021 flood in Belgium,
Germany and the Netherlands, answered on the organisers' data; the EU-wide findings
below give the recommendations their scale and actor.

**The core, in four figures** (first Copernicus EMS maps, residents from GHS-POP E2020,
read by `src.policy_tool.hero()` from `event_2021_*.parquet`):

- Eschweiler (EMSR517 AOI09): **91 %** of the 1,213 residents the water reached (1,107)
  lived outside the JRC 1-in-100-year flood zone. Ahr valley (AOI15): **51 %** of 3,739.
- Germany: **375** buildings graded destroyed on the first maps (792 with the later
  maps); the water reached **32,562** residents, **12,238** outside the zone.
- Belgium: 1,994 residents reached (12.4 % outside the zone); Netherlands: 2,449
  (11.7 %). Neither has damage-grading products, so no destroyed count exists. The
  Belgian 12.4 % is a floor: radar maps stop at walls, and against the extent Wallonia
  recorded on the ground 40 to 51 % of the residents reached were outside the zone
  (`decisions.md`, 2026-10-25). The 1,994 covers both Belgian EMS maps; Liège alone
  (EMSR518 AOI01) is the 1,356 the brief quotes.

These are counts on a 1 km population grid spread evenly over each cell, so read
Eschweiler as about 90 % of about 1,100 people. Eschweiler sits on a small river the
European map does not model (it covers basins above 150 km²), so its 91 % says where the
map stops, not how wrong it is inside its scope.

> Being at risk of flooding and being unprepared for it are two different maps. Europe
> governs the first one and reports the second one badly.

## 1. The measured base

`exposure.parquet` holds every NUTS3 region at nine return periods; `context.parquet`
one row per region. At the 1-in-100-year river flood (undefended): **about 25.7 million**
EU-27 residents exposed (25,737,004 in the table), **5.8 %** of the EU-27 population
(446,267,469). Over all 37 countries in the table it is 29,727,887 people (5.3 %). Quote
it rounded: it is a modelled extent over a 1 km population grid, and the maps reproduce
about two thirds of observed flood extents (Dottori et al. 2022).
EU-27 exposure grows with the period (RP10 16.7 million, RP100 25.7 million, RP500 30.7
million); extents are nested, so quote the return period with every headcount.

The most exposed EU-27 regions by share are Dutch, Italian, German and Hungarian
(Zuidoost-Zuid-Holland 70.8 %, Zuidwest-Gelderland 68.9 %, Rovigo 61.1 %), and all ten
sit behind defences: behind the PESETA IV design standards (`residual_exposed_pop_rp100`)
at most 1.1 % of their population remains exposed. Behind the standards the leaders are
Pisa, Trier, Vidin, Firenze, Frankenthal (Pfalz), Lucca. The standards date from 2019
and are design levels, not guarantees.

## 2. Four findings, with their caveats

### 2.1 The Member States' risk declaration is not comparable between them

Under **Article 5** of [Directive 2007/60/EC](https://eur-lex.europa.eu/eli/dir/2007/60/oj)
each State reports its Areas of Potential Significant Flood Risk (APSFR). On the EEA
layer (2018 cycle, 12,173 polygons, 25 countries) the declared share of national
territory runs from 99.9 % (Belgium, one giant polygon) to 0.004 % (Spain, Cyprus), a
factor of about 23,000; Germany's polygons are river-reach ribbons (shape index about
51), Belgium's a zone (1.5). Any pan-European statistic built on declared APSFR area
ranks reporting styles, not risk. It is not evidence that a State under-declares: a State
may have assessed an area under Article 4 and found the risk not significant.

### 2.2 Two EU-27 Member States are absent from the Commission's layer

Pinning the 2018 cycle (as `src/apsfr.py` does) drops Lithuania, which reported in 2010
only; Ireland appears in neither cycle. Ireland runs the CFRAM programme, so this is a
gap in the published reporting, not in Irish policy.

### 2.3 Most exposed people are downstream of someone else

Off the WFD river basin districts grouped by `config/international_basins.yaml`, about
60 % of EU-27 exposed residents at RP100 (52 % over all 37 countries) live in a basin that
crosses a national border. Each region counts in proportion to the share of its area in
such a basin, so a region that only touches one at its edge adds little. This is a floor: Switzerland, Belarus,
Ukraine and Serbia do not report under the
[Water Framework Directive](https://eur-lex.europa.eu/eli/dir/2000/60/oj), and districts
the crosswalk cannot group stay national.

### 2.4 The reference discharge is rising where people already live in the way

EURO-CORDEX under RCP 8.5: eight bias-adjusted simulations through two hydrological
models, 16 members per horizon. Median regional change in reference discharge across the
EU-27 is about +10 % (2011-2040), +21 % (2041-2070) and +28 % (2071-2100); "robust" means at least 80 %
of members agree on the sign (IPCC AR6), with unanimity reported beside it. The 16
members are 8 independent simulations, so 80 % means about 7 of 8. About 70 EU-27
regions are in the top decile of exposure share today and robustly rising by 2041-2070: a
planning list, not a ranking, to be read beside the residual-exposure list (only a few
regions are on both). The observed record (HERA v2, 1991-2020) does not show the rise
yet; a trend not significant over 30 years is not evidence of no change.
**Article 14(4)** requires that the likely impact of climate change be taken into account
in the review, so this is the finding the law explicitly asks for.

## 3. The calendar (Directive text, `data/raw/scrape/floods_directive.html`)

| Instrument | Article | Reviewed by | Then every | Next date |
|---|---|---|---|---|
| Preliminary flood risk assessment | 14(1) | 22 Dec 2018 | six years | 22 Dec 2030 |
| Flood hazard and flood risk maps | 14(2) | 22 Dec 2019 | six years | 22 Dec 2031 |
| **Flood risk management plans** | 14(3) | 22 Dec 2021 | six years | **22 Dec 2027** |
| Member States inform the Commission | 15 | - | - | within three months of the above |
| Commission report to Parliament and Council | 16 | 22 Dec 2018 | six years | 22 Dec 2030 |

The first two date columns are the Article's own words (`src.legislation.cite("FD",
"14(3)")` returns them with the ELI URL); the last is arithmetic. The plan review of
**22 December 2027** is the one open instrument. Three more articles do real work:
**7(4)** (a plan shall not significantly increase flood risk in another country of the
basin, unless coordinated under Article 8), **8(5)** (an issue a State cannot resolve
alone may be reported; the Commission shall respond within six months) and **8(3)**
(beyond the Union States only "shall endeavour" to produce a single plan, which is
finding 2.3 in the law's words).

## 4. Three recommendations, none needing new legislation

The regional brief in `docs/hackathon/` speaks to one crisis coordinator for
Liège-Limburg-Aachen: share one risk picture, pair every warning with where to go, spend
on the right lever. Its third action cites Article 8(2), coordination towards one plan
per international district, and Article 14, the 2027 review. The three below take the
same story to the EU level. R1 and R2 rest on the EU-wide layer (findings 2.1 and 2.2),
not on July 2021. R3 carries the regional brief's cross-border point one step further:
Article 8(5) is the route that makes the Commission answer when 8(2) coordination stalls.

**R1. Make the Article 5 declaration comparable before the 2027 review.**
*What:* reporting guidance fixing the geometry convention for APSFR (minimum mapping unit;
buffered area or line) and publishing the declared share of territory with each submission.
*By whom:* DG Environment through the Working Group on Floods, with the EEA as custodian
of the layer. *How:* an amendment to the next cycle's guidance. *By when:* tabled early
2027. *Evidence:* 2.1.

**R2. Close the two reporting holes and publish absence as absence.**
*What:* Ireland's APSFR into the published layer; Lithuania's current cycle reconciled;
the service saying so where a State is absent. *By whom:* the EEA, with the Irish Office
of Public Works and the Lithuanian Environmental Protection Agency; DG ENV as guardian.
*How:* Article 15 reporting. *By when:* before the Commission's report under Article 16
(22 Dec 2030). *Evidence:* 2.2.

**R3. Use Article 8(5) on one named shared basin as a test case.**
*What:* one State formally reports under Article 8(5) that it cannot resolve coordination
in a shared basin and recommends a solution; the Commission owes an answer in six months.
*Where:* the Meuse (five states, secretariat in Liège; Namur reads `[DE, FR, LU, NL]`); for
the non-EU upstream problem the Rhine (Switzerland) or the Danube (Serbia). *By whom:* the
International Meuse Commission as forum, one party as reporter, the Commission as
respondent. *By when:* mid-2027, inside the planning window. *Evidence:* 2.3.

Addressees: [DG Environment - Floods](https://environment.ec.europa.eu/topics/water/floods_en),
[EEA WISE](https://water.discomap.eea.europa.eu/), the International Meuse, Scheldt, Rhine
(ICPR) and Danube (ICPDR) commissions, the
[JRC Risk Data Hub](https://drmkc.jrc.ec.europa.eu/risk-data-hub), the EU Solidarity Fund
and EIOPA (insurance protection gap).

## 5. The responsible-AI layer

The grid is the HLEG seven requirements ([responsible_ai.md](responsible_ai.md)). Legal
context: [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)
(AI Act) and its amendment Regulation (EU) 2026/1744 (Digital Omnibus on AI). Do not
assert Annex III high-risk classification without reading the annex; the defensible
framing is a decision-support tool for a public authority to which the transparency and
human-oversight expectations were applied anyway. The Cloud and AI Development Act is a
proposal, not adopted.

## 6. What this page does not claim

- No State is accused of under-declaring: 2.1 and 2.2 concern a published layer.
- No casualty or loss figure: Risk Data Hub rows are nested by administrative level and
  averaged across DFO, EM-DAT and HANZE; an unfiltered sum counts an event four times.
- No prediction: the hazard layer models river flooding only, for basins above about
  150 km2, and omits surface runoff, a large part of what happened in Wallonia in 2021.
- The cross-border figures are a floor; the climate figures are medians and quartiles.
- No figure here is a statutory hazard or risk map; where it disagrees with a Member
  State's map, theirs is the one the law reads. When quoting a return period, say which
  Article 6(3) class it is read in: the Article puts a number on the medium class only
  (likely return period of 100 years or more); calling RP10-RP75 "high probability" is
  this kit's reading.
- The poverty rate carries its unit in its name (`poverty_rate_pct`); an older frozen
  `exposure.parquet` still says `poverty_rate`, and the API and UIs read both.

More: [limitations.md](limitations.md).

# EU Flood-Risk Policy Framework — Reference Report

**Compiled:** 2026-10-05 · **For:** European AI Challenge 2026 (JRC × FARI, 29–30 Oct 2026) · **Use:** RAG corpus + policy brief (Annex 6 template)

**Verification legend:** ✅ fetched and read the primary source in this session · ⚠️ secondary/press source only · ❌ could not verify

**Local copies.** The documents below are now declared in `config/sources.yaml`
and fetched to stable paths by `python -m src.fetch`, so they survive a session
and a fresh clone. The earlier version of this section pointed at a temporary
session scratchpad that no longer exists.

| Document | On disk after a fetch |
|---|---|
| Walloon parliamentary inquiry report, 24 Mar 2022, 161 recommendations (20.1 MB) | `data/raw/scrape/wallonia_inquiry_commission_2022.pdf` |
| JRC135679 — CEMS assessment of EFAS during the Rhine/Meuse floods, July 2021 (7.5 MB) | `data/raw/scrape/efas_assessment_rhine_meuse_2021.pdf` |
| EFAS bimonthly bulletin, June–July 2021 (4.4 MB) | `data/raw/scrape/efas_bulletin_jun_jul_2021.pdf` |
| Walloon circular on building in flood-prone zones (2.2 MB) | `data/raw/scrape/wallonia_circular_building_in_flood_zones.pdf` |
| Environmental impact report of the PGRI 2022–2027 (6.6 MB) | `data/raw/scrape/wallonia_flood_risk_management_plan_rie.pdf` |
| Sendai Framework, English (1,022,502 B, manual step — `sources.yaml` declares the landing page, not the PDF) | `data/raw/download/43291_sendaiframeworkfordrren.pdf` — fetchable directly from `unisdr.org/files/`, HTTP 200 on 6 Oct 2026; it is UNDRR's own `/media/16176/download` link that is JS-gated and returns HTML |

**Most of what this report cites is not declared.** Diffing the sources named
below against the ids in `config/sources.yaml` (6 October 2026): declared and
fetched are Directive 2007/60/EC, JRC135679, the EFAS bulletin, the PGRI
environmental report, the Walloon circular, Walloon Parliament Doc. 894,
Regulation (EU) 2024/1689, the HLEG guidelines, the Sendai Framework and the JRC
repository search — ten of the twelve `policy_corpus`/`context` entries, which is
the whole policy corpus the kit fetches.

Undeclared, with no local copy, are at least thirteen: Commission Recommendation
2023/C 56/01 · Decision 1313/2013/EU (UCPM) · COM(2021) 82 · COM(2025) 280 ·
EEA Report 01/2024 (EUCRA) · the EEA economic-losses indicator (14 Oct 2025) ·
EIOPA-BoS-25/564 · the EIOPA dashboard input `.xlsx` · Regulation (EU) 2026/1744 ·
the Commission Staff Working Documents SWD(2025) series · the Walloon Government
press release of 4 July 2022 · the Assuralia press release of 30 January 2023 ·
the Belgian Insurance Act of 4 April 2014. The ALTAI assessment list (open item
11) was never fetched either.

That matters in a specific way rather than in general: the retrieval layer refuses
to answer from a document it does not hold, so **every figure above that comes
from one of those thirteen is unciteable by the kit itself** and has to be either
declared in `sources.yaml` and fetched, or carried into the brief as a manual
citation with its URL. Do the first for anything the brief's argument rests on.

**Declared on 12 October 2026: twelve of the thirteen.** In `policy_corpus`:
`union_disaster_resilience_goals`, `ucpm_decision`, `eu_adaptation_strategy_2021`,
`water_resilience_strategy_2025`, `floods_directive_assessment_swd_2025_24`,
`ai_act_digital_omnibus_2026` (the six EU acts, fetched from the Publications
Office's CELLAR because eur-lex answers every script with a WAF challenge),
`eea_eucra_2024`, `eea_economic_losses_indicator`,
`eiopa_protection_gap_nutshell_2025`, `wallonia_floods_review_2022`,
`assuralia_floods_update_2023`; in `context`, `eiopa_protection_gap_dashboard_data`
(a spreadsheet, which the retrieval layer does not read). They are citable once
`python -m src.fetch` has run. Three gaps remain, each a manual citation:

- **Belgian Insurance Act of 4 April 2014.** Its official text is
  `https://www.ejustice.just.fgov.be/eli/loi/2014/04/04/2014011239/justel`, and
  that host's robots.txt disallows the path (checked 2026-10-12), so the kit
  does not fetch it.
- **The SWD(2025) series** is one document per Member State; only Spain's,
  SWD(2025) 24, has a recorded CELEX number and is declared.
- **EEA Report 01/2024 (EUCRA)** is declared as its landing page; the report
  PDF's address was not resolved.

---

## 1. Floods Directive 2007/60/EC

**Exact EUR-Lex URLs** ✅
- Original act: `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32007L0060`
- ELI (preferred for citation): `https://eur-lex.europa.eu/eli/dir/2007/60/oj/eng`
- OJ reference: OJ L 288, 6.11.2007, pp. 27–34. Full title: *Directive 2007/60/EC of the European Parliament and of the Council of 23 October 2007 on the assessment and management of flood risks*.

**The three-stage cycle** ✅ (read from the directive text)

| Stage | Article | First-cycle deadline |
|---|---|---|
| 1. Preliminary flood risk assessment (PFRA) — identify "areas of potential significant flood risk" from available information, past floods and climate-change impact | Art. 4 (+ Art. 5 identification of APSFR) | **22 December 2011** |
| 2. Flood hazard maps and flood risk maps — three scenarios: low probability / extreme; medium probability (return period ≥ 100 years); high probability. Must show extent, water depths or level, and where relevant flow velocity | Art. 6 | **22 December 2013** |
| 3. Flood risk management plans (FRMPs) — appropriate objectives + measures, focused on **prevention, protection and preparedness**, incl. flood forecasting and early warning systems | Art. 7 (content in Annex A) | **22 December 2015** |

**Review/update cycle — Article 14 (6-yearly); climate change must be factored into the PFRA and FRMP reviews (Art. 14(4) names paragraphs 1 and 3, not the map review)** ✅
- PFRA: reviewed by 22 Dec 2018, then every 6 years
- Maps: reviewed by 22 Dec 2019, then every 6 years
- FRMPs: reviewed by 22 Dec 2021, then every 6 years

**Reporting:** Art. 15 — Member States report each deliverable to the Commission within **3 months** of the respective deadline (via WISE/Reportnet).

**Current cycle** ✅ (Commission "Floods" page, last updated 2 July 2025, `https://environment.ec.europa.eu/topics/water/floods_en`)
- Cycle 1: 2010–2015 · Cycle 2: 2016–2021 · **Cycle 3 (current): 2022–2027**
- Derived third-cycle deadlines (Art. 14 arithmetic, 2018/2019/2021 + 6): PFRA review **22 Dec 2024** (done), updated hazard & risk maps **22 Dec 2025**, third-generation FRMPs **22 Dec 2027**. ⚠️ The 2024/2025/2027 dates are arithmetic from Art. 14 and are corroborated by national implementing authorities (e.g. Italy's MASE geoportal, DfI Northern Ireland), not by a single Commission page stating all three.
- Commission assessment of the **second** cycle: Commission Staff Working Documents SWD(2025) series, dated **4 February 2025**, one per Member State, e.g. SWD/2025/24 final (Spain) at `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex:52025SC0024` ✅. Headline message (Commission wording; it does not appear in the SWD(2025) 24 text on disk): "faster progress is needed across Europe to protect waters and better manage flood risks."
- **Hackathon-relevant hook:** Belgium/Wallonia is in the window where the third FRMP (PGRI 2028–2033) is being drafted — an AI tool that helps assemble or quality-check PFRA/map/FRMP inputs lands on a live deadline.

---

## 2. EU Adaptation Strategy + 2024–2026 climate-resilience developments

**EU Adaptation Strategy** ✅ `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A52021DC0082`
- *"Forging a climate-resilient Europe – the new EU Strategy on Adaptation to Climate Change"*, **COM(2021) 82 final, 24 February 2021**. Portal page: `https://climate.ec.europa.eu/eu-action/adaptation-climate-change/eu-adaptation-strategy_en`
- Four objectives: adaptation that is **smarter, faster and more systemic**, plus **stepping up international action**. Vision: a climate-resilient EU by 2050.
- Two quotable figures from the Strategy itself ✅: *"only 35% on average of the climate-related economic losses are insured, and as low as 5% or less in some parts of Europe"*; *"In the EU, these losses already average over EUR 12 billion per year."* (2021 baseline — note it is now superseded by the EEA 2025 indicator below.)

**EUCRA — European Climate Risk Assessment** ✅ `https://climate-adapt.eea.europa.eu/en/eu-adaptation-policy/key-eu-actions/european-climate-risk-assessment`; report: EEA Report 01/2024, `https://www.eea.europa.eu/en/analysis/publications/european-climate-risk-assessment`
- First-of-its-kind, published **March 2024**. Identifies **36 major climate risks** for Europe in five clusters (ecosystems, food, health, infrastructure, economy & finance) plus 3 risks specific to outermost regions; **8 risks judged especially urgent**, among them *risks to people and infrastructure from inland (river/pluvial) flooding*.
- EUCRA figures (⚠️ via EUCRA executive summary / EEA summary pages, not re-read line-by-line in the full report): floods have cost **more than EUR 170 billion since 1980**; **coastal flood** losses could exceed **EUR 1 trillion per year by 2100** under high-warming scenarios; annual climate damage to European infrastructure rising from **EUR 9.3 bn (2020s) to EUR 37.0 bn (2080s)**.

**Key figures on flood damages in Europe — the number to use** ✅ EEA indicator *"Economic losses from weather- and climate-related extremes in Europe"*, **published 14 October 2025**, `https://www.eea.europa.eu/en/analysis/indicators/economic-losses-from-climate-related`
- **EUR 822 billion** total economic losses in the **EU, 1980–2024** (2024 prices). Over **EUR 208 billion (25%)** of that occurred in **2021–2024 alone**.
- Breakdown: **hydrological hazards (floods) 47%** (≈ EUR 386 bn) — the single largest category; meteorological (storms, hail, lightning) 27%; climatological (heatwaves) 18%; other (drought, wildfire, cold/frost) 8%.
- **Less than 20%** of total losses were privately insured. By hazard: meteorological (storms, hail, lightning) >35% insured, **hydrological ≈15%**, climatological ≈10%.

> ⚠️ **Flag a reconcilable discrepancy:** EUCRA's "more than EUR 170 bn for floods since 1980" vs the EEA indicator's 47% of EUR 822 bn ≈ EUR 386 bn. Different vintages (2024 vs 2025 publication), different price bases/inflation adjustment and (probably) different hazard scoping. **Use the EEA 2025 indicator figure and cite it with its date**; do not present both as the same quantity.

**2024–2026 developments — the live policy window**
- **European Water Resilience Strategy**, **COM(2025) 280 final, 4 June 2025** ✅ `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52025DC0280`. Introduces a **"Water Efficiency First"** principle and a target to improve EU water efficiency by **at least 10% by 2030**; commits the Commission to improve **early warning and real-time monitoring for floods and droughts** and to strengthen EU–national–local links.
- **European Climate Adaptation Plan (ECAP) / European integrated framework for climate resilience and risk management** ⚠️ — announced in von der Leyen's 2024–2029 Political Guidelines, led by Commissioner Hoekstra. Commission pages: `https://climate.ec.europa.eu/areas-action/adaptation-and-resilience-climate-change/european-climate-resilience-and-risk-management-integrated-framework_en` and `https://climate-adapt.eea.europa.eu/en/eu-policy/eu-adaptation-policy/european-climate-adaptation-plan`. Expected as a package (Communication + a legislative proposal for a Regulation + a Recommendation + a Commission Decision), reportedly scheduled for **20 October 2026** — i.e. **nine days before the hackathon**. Reported design features: a **"climate resilience by design"** principle, a **3 °C global-warming reference scenario**, mandatory ownership of major climate risks, an **EU climate viewer**, and support for local authorities. ❌ As of this research the adopted text is not yet on EUR-Lex — treat the content as *announced/expected*, verify on the day, and write the brief so it works either way.

---

## 3. Sendai Framework for Disaster Risk Reduction 2015–2030

**Canonical URL:** `https://www.undrr.org/publication/sendai-framework-disaster-risk-reduction-2015-2030` ✅ — **HTTP 200 to a scripted fetch**, re-checked 6 October 2026, and `src.fetch` already holds it at `data/raw/scrape/sendai_framework.html` (51,144 B, `error: null` in `data/raw/manifest.json`). The overview page `https://www.undrr.org/implementing-sendai-framework/what-sendai-framework` also returns 200. The verbatim text below still comes from the official framework PDF ✅ `https://www.unisdr.org/files/43291_sendaiframeworkfordrren.pdf` (1,022,502 B, HTTP 200, measured the same day), for the reason that survives the correction: the canonical URL is a *publication landing page*, so the HTML on disk carries the record and not the framework's own wording. What is still gated is UNDRR's own `/media/16176/download` link, which answers 200 with `text/html` — a JS stub, not the PDF — so take the PDF from `unisdr.org` and not from there.

Adopted at the Third UN World Conference on DRR, **Sendai, Japan, 14–18 March 2015** (adopted 18 March 2015); endorsed by UN General Assembly **resolution 69/283**.

**Expected outcome** (verbatim) ✅
> "The substantial reduction of disaster risk and losses in lives, livelihoods and health and in the economic, physical, social, cultural and environmental assets of persons, businesses, communities and countries."

**Goal** (verbatim) ✅
> "Prevent new and reduce existing disaster risk through the implementation of integrated and inclusive economic, structural, legal, social, health, cultural, educational, environmental, technological, political and institutional measures that prevent and reduce hazard exposure and vulnerability to disaster, increase preparedness for response and recovery, and thus strengthen resilience."

**Four Priorities for Action** (verbatim headings) ✅
1. **Priority 1: Understanding disaster risk**
2. **Priority 2: Strengthening disaster risk governance to manage disaster risk**
3. **Priority 3: Investing in disaster risk reduction for resilience**
4. **Priority 4: Enhancing disaster preparedness for effective response and to "Build Back Better" in recovery, rehabilitation and reconstruction**

**Seven global targets** (verbatim, (a)–(g)) ✅
- **(a)** "Substantially reduce global disaster mortality by 2030, aiming to lower the average per 100,000 global mortality rate in the decade 2020–2030 compared to the period 2005–2015";
- **(b)** "Substantially reduce the number of affected people globally by 2030, aiming to lower the average global figure per 100,000 in the decade 2020–2030 compared to the period 2005–2015";
- **(c)** "Reduce direct disaster economic loss in relation to global gross domestic product (GDP) by 2030";
- **(d)** "Substantially reduce disaster damage to critical infrastructure and disruption of basic services, among them health and educational facilities, including through developing their resilience by 2030";
- **(e)** "Substantially increase the number of countries with national and local disaster risk reduction strategies by 2020";
- **(f)** "Substantially enhance international cooperation to developing countries through adequate and sustainable support to complement their national actions for implementation of the present Framework by 2030";
- **(g)** "Substantially increase the availability of and access to multi-hazard early warning systems and disaster risk information and assessments to people by 2030."

**Flood relevance / mapping to the EU instruments**
- Priority 1 ↔ Floods Directive Art. 4–6 (PFRA, hazard & risk maps); Priority 2 ↔ Art. 7 FRMPs and the UCPM Art. 6 risk-management planning; Priority 3 ↔ protection/NbS measures; Priority 4 ↔ early warning, EFAS/BE-Alert, "Build Back Better" ↔ Wallonia's resilient-reconstruction programme.
- **Target (g)** is the single most directly actionable one for an AI flood-warning use case, and it is the one the Walloon 2021 experience failed on (see §6).
- Target (c) is the hook for the damage figures in §2; target (d) for the 559 damaged bridges in §6.

---

## 4. EU Civil Protection Mechanism, rescEU, and the Union Disaster Resilience Goals

**UCPM** ✅ `https://civil-protection-humanitarian-aid.ec.europa.eu/what/civil-protection/eu-civil-protection-mechanism_en` (page dated 4 August 2026)
- Legal basis: **Decision No 1313/2013/EU of 17 December 2013 on a Union Civil Protection Mechanism** ✅ `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32013D1313` (as amended, notably by Regulation (EU) 2021/836). Mechanism originally established in **October 2001**.
- **37 states**: all 27 EU Member States + Albania, Bosnia and Herzegovina, Iceland, Moldova, Montenegro, North Macedonia, Norway, Serbia, Türkiye, Ukraine.
- **ERCC (Emergency Response Coordination Centre)** — "the operational heart of the UCPM", monitoring events 24/7 and coordinating/co-financing assistance on request from an affected state.
- Floods are named among the most common triggers of the Mechanism.
- **Article 6 of Decision 1313/2013/EU** ✅ obliges Member States to develop **national/sub-national risk assessments** and **disaster risk management planning**, to provide summaries of risk assessments to the Commission (first by 22 December 2015, then every three years) and to submit risk-management-capability assessments. This is the article that makes flood risk assessment a standing legal duty of a *public authority* — the exact actor in the AI-governance question in §7.

**rescEU** ✅ `https://civil-protection-humanitarian-aid.ec.europa.eu/what/civil-protection/resceu_en` (page last updated 11 August 2026)
- "A strategic reserve of European disaster response capabilities and stockpiles, **fully funded by the EU**", created as an upgrade to the UCPM (2019 reform).
- Current reserve components named on the page: firefighting aircraft and helicopters (12 new planes planned for 6 countries; 5 new helicopters), medical evacuation aircraft and emergency medical teams, strategic medical and CBRN stockpiles (**22 rescEU stockpiles across 16 Member States, 17 fully operational**), emergency shelter reserves (**7 Member States**), transport and logistics assets (2 cargo/personnel aircraft), and thousands of power generators.
- ⚠️ **Flood-specific caveat to state honestly in the brief:** the rescEU page lists **no flood-specific reserve** (no flood-containment barriers, no high-capacity pumping modules) as of 11 Aug 2026. Flood response capacity sits instead in the **European Civil Protection Pool** national modules (e.g. High Capacity Pumping / HCP, Flood Containment, Flood Rescue using Boats — defined in the UCPM implementing rules), not in the EU-owned rescEU reserve. ❌ I did not fetch the implementing-decision annex listing those module specifications; verify before asserting module names/capacities.

**Union Disaster Resilience Goals** ✅ `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A32023H0215%2801%29`
- **Commission Recommendation of 8 February 2023 on Union disaster resilience goals**, OJ **C 56, 15.2.2023, p. 1** (2023/C 56/01), accompanied by a Communication the same day. **Non-binding** common baseline for prevention and preparedness against disasters with multi-country/transboundary effects.
- The five goals, verbatim:
  1. **Anticipate** — "improving risk assessment, anticipation and disaster risk management planning"
  2. **Prepare** — "increasing risk awareness and preparedness of the population"
  3. **Alert** — "enhancing early warning"
  4. **Respond** — "enhancing the Union Mechanism response capacity"
  5. **Secure** — "ensuring a robust Civil Protection System"
- Two directly quotable flood passages ✅:
  > Goal 3 objective: *"To enhance, by 2030, the effectiveness and interoperability of early warning systems in the Union to allow a timely and effective response to disasters and avoid or reduce their adverse impacts, …"*
  > Goal 4 (flood benchmark): *"The Union Mechanism should at least be able to respond to a flooding event affecting at least three Member States simultaneously with overwhelmed national response capacities."*
- Also: *"effective early warning and monitoring systems are critical to anticipate and prepare for disasters."*

**EFAS / Copernicus EMS** (the operational layer — see §6 for its 2021 performance): `https://european-flood.emergency.copernicus.eu/`. EFAS is run under the Copernicus Emergency Management Service with the **JRC** as operator; its notifications go to EFAS partners, third-party partners and the **ERCC**, linking §4 and §6.

---

## 5. The insurance protection gap for floods in Europe (EIOPA dashboard)

**Source (authoritative, read in full)** ✅
- Dashboard landing page: `https://www.eiopa.europa.eu/tools-and-data/dashboard-insurance-protection-gap-natural-catastrophes_en` (page states "Last updated on 05 December 2025")
- "In a nutshell" document: **EIOPA-BoS-25/564, dated 10 November 2025**, `https://www.eiopa.europa.eu/document/download/bbdc653b-e335-41f0-8293-0d8280a09855_en` ✅ read cover-to-cover
- Technical description: **EIOPA-BoS-24/472**, `https://www.eiopa.europa.eu/document/download/3e9c5e07-1be0-4be1-9fad-37970eb35a04_en`
- Raw input data (per-country, per-peril, 2022–2025): **EIOPA-BoS-24/474** `.xlsx`, `https://www.eiopa.europa.eu/document/download/d507df26-1ee3-43f8-858e-ad1882bc89de_en` ✅ parsed

**What it measures** ✅
- Purpose: "to monitor the risks related to the insurance protection gap for Nat Cat in Europe", to identify at-risk regions and the **underlying drivers** of the gap, not just its size.
- Two views:
  - **Historical protection gap** — from observed economic vs insured losses (**1980–2024**), sourced from **EM-DAT** and **CATDAT** (RiskLayer GmbH, under institutional agreement), reviewed by national competent authorities (NCAs).
  - **Current protection gap** — a *modelled* estimate combining **hazard, exposure, vulnerability** (together: the risk) with **insurance coverage/penetration** at present time.
- Output is a **protection-gap score per country per peril** (scale ≈0–4; **≥3 = relevant protection gap**, **2.5 = country to monitor**, **4 = very high**), plus a per-country **total score** summed across the five perils, plus a descriptive **country insurance scheme** view (public / public-private / private-only, mandatory or not, deductibles, limits).
- **Five perils covered:** **windstorm, wildfire, flood\*, coastal flood, earthquake**. Footnote, verbatim: *"Flood\* is covering pluvial and fluvial flooding, not including coastal flooding."* Drought and heatwave are listed only in the outlook as candidates for future addition.
- The 2025 release is explicitly a **"light update"** of the 2024 dashboard (updated loss data, GDP and EUR/USD rates, light review of risk estimation and scheme descriptions); fuller reviews are planned "~every 5 years".

**What it says about floods** ✅ (all verbatim or directly derived)
- Headline: *"Only around a quarter of the losses were insured in the past (1980–2024) in Europe."*
- Floods dominate the **absolute** uninsured loss: *"three peril regions show the highest uninsured losses: Italy Earthquake, Italy Flood\* and Germany Flood\* which corresponds to ~43% of the uninsured losses in Europe."* Of those historical losses, **98%** (Italy earthquake), **97%** (Italy flood\*) and **74%** (Germany flood\*) were **uninsured**. Their shares of all EEA uninsured losses: 18%, **14%**, **11%** respectively — i.e. **Italy + Germany flood alone = 25% of Europe's entire uninsured nat-cat loss**.
- **Current flood\* protection gap (2025):** **Romania and Croatia** have a relevant gap (score ≥3). **Seven to eight countries to monitor** (score 2.5): Austria, Bulgaria, Czechia, Germany, Italy, Netherlands, Poland, Slovenia. *(The nutshell text says "Seven countries" and then lists eight — a drafting inconsistency in EIOPA's own document; flag it rather than silently pick one.)*
- **Coastal flood (2025):** only the **Netherlands** shows a gap (score ≥3); **Germany** to monitor (2.5). EIOPA notes coastal flood is "a peril which could be more relevant with regard to climate change."
- Worst overall: **Greece and Italy, total score 12** (high hazard + very low penetration, chiefly earthquake). Lowest overall gap peril: windstorm (all countries ≤2).

**What it says about Belgium** ✅ (nutshell + parsed raw data file)

| Belgium, 2025 dashboard | Flood\* | Windstorm | Coastal flood | Earthquake | Wildfire |
|---|---|---|---|---|---|
| Economic losses 1980–2024, CATDAT (EUR m, adj.) | **12,540** | 6,463 | 0 | 177 | 0 |
| Insured losses (EUR m, adj.) | **2,739** | 2,070 | 0 | 0 | 0 |
| **% insured / % uninsured** | **22% / 78%** | 32% / 68% ⚠️ | – | 0% / 100% | – |
| Historical score | **2.5** | 2 | n/a | 1 | n/a |
| Risk estimation | **2.5** | 2.7 | 2 | 1.5 | 1 |
| Insurance penetration score | **1** (best) | 1 | 1 | 1 | 1 |
| **Current (estimated) score** | **1.5** | 1.5 | 1 | 1 | 1 |

- ⚠️ **The windstorm split is re-derived from this table's own loss figures, not transcribed from EIOPA.** 2,070 / 6,463 = **32.0% insured**, hence **68% uninsured**. The pairing "32% / 53.5%" that circulates for this row cannot be an insured/uninsured split, because the two do not sum to 100. The `.xlsx` on disk shows what 53.5% is: EIOPA's own "Uninsured losses (%)" column, which for this row is 100 minus the mean of the CATDAT insured share (32%) and the EM-DAT one (61%). For flood\* the EM-DAT insured share is 0 and the column reads 78% = 100 − 22%. So 53.5% is a two-database figure, not the CATDAT complement; never present it as the complement of 32%.
- **Belgium's total current protection-gap score = 6** in 2022, 2023, 2024 and 2025 (unchanged). For comparison: EEA aggregate **5.5** (2025), Greece and Italy **12**, Croatia **11**, Romania **11.5**, Netherlands **9.5**, Germany **8**, Sweden/Finland/Estonia/Iceland/Liechtenstein **4** (lowest).
- EIOPA's own country comment on Belgium, verbatim ✅:
  > Historical: *"The historical losses show the highest protection gap for flood\*. The protection gap for other perils in Belgium is low (score ≤2). … The considered databases did not include any losses for coastal flood and wildfire for Belgium."*
  > Current: *"Windstorm and flood\* are the highest risks in Belgium. The insurance penetration is between 75% and 100% for all perils. The current protection gap in Belgium is low as the perils with high risks have a high insurance penetration."*
- **The Belgian paradox to put in the brief:** Belgium's *forward-looking* flood gap is **low (1.5)** because insurance penetration is near-universal — Belgium is one of the countries EIOPA names as having a structured national scheme ("Similar examples can be found in Norway, **Belgium**, France and Iceland, among others"). Yet its *historical* flood gap is its worst score (2.5) with **78% of 1980–2024 flood losses uninsured**. Belgium's gap is therefore **not a penetration problem but a capacity/limits problem** — which is exactly what July 2021 exposed (see §6: statutory insurer caps would have paid out only 20% without a EUR ~1 bn public top-up).
- **Why penetration is high (Belgian legal basis)** ⚠️: since 2005, and maintained in the **Insurance Act of 4 April 2014 (Art. 123 et seq.)**, cover against natural catastrophes — including **flood** (water from below), earthquake, sewer overflow/backup, and landslide/subsidence — is a **mandatory extension of fire insurance for "simple risks"** (property insured value up to ≈ EUR 1.45 m). Sources: FPS Economy `https://economie.fgov.be/en/themes/financial-services/insurance/fire-and-natural-disaster`; Lloyd's market bulletin "Insurance of simple risks against natural catastrophe in Belgium". Assuralia's release of 30 January 2023 (on disk) dates the obligation to 2007 ("Depuis 2007") and puts the capped payout in Art. 130 of the Insurance Act. ❌ I did not read the statutory text itself — verify Art. 123 wording and the current indexed "simple risk" threshold before quoting them in the brief.

---

## 6. July 2021 Belgium floods — official figures and post-event evaluations

### Official figures (Walloon Government, press release *"Inondations de juillet 2021 : Bilan et perspectives"*, **4 July 2022**) ✅ read in full
`https://www.wallonie.be/sites/default/files/2022-07/[CP] - Inondations de juillet 2021 - Bilan et perspectives.pdf`

- Event date: **14 July 2021** — "les pires inondations de son histoire moderne" (the worst floods in Wallonia's modern history).
- **209 of 262 Walloon communes** affected. Hardest hit: Province of Liège and the **Vesdre valley**.
- **39 deaths** — "Selon la police, 39 personnes sont malheureusement décédées."
- **100,000 people affected** (*sinistrées*).
- **9,670 hectares** under water.
- **≈48,000 buildings**, of which **45,000 dwellings**; **>11,000 cars**; **559 bridges** damaged; 160 sports facilities damaged; hundreds of engineering structures destroyed or damaged.
- Day after: **15,000 households without gas, 66,500 without electricity, 47,000 without water**.
- **Cost to the Walloon Region: EUR 2.8 billion** ("À ce stade, le coût des inondations de juillet 2021 pour la Région wallonne est de 2,8 milliards d'euros").
- **The insurance mechanism — the key protection-gap fact** ✅ verbatim-sourced: a **federal law allows insurers to cap payouts** in a large-scale catastrophe; under that cap *"les assurés n'auraient touché que 20% du montant des dégâts estimés par leur assureur"* (policyholders would have received only **20%** of their assessed damage). The Walloon Government made *"un effort financier sans précédent d'un milliard d'euros"* (**EUR 1 billion**) so insured victims could be fully compensated; after negotiation insurers nearly doubled their intervention ceiling, giving a final split of **insurers 41% / Government 59%**.
- Calamity Fund (for the **uninsured**): **7,673** compensation claims covering 10,640 asset types; **1,911 positive decisions, 1,696 refused** as non-compliant with the decree criteria. Fund staffing went from **3 to 41** agents.
- Other: **EUR 80 million** to affected communes (category 1 communes received >EUR 51 m in total: Liège EUR 8.25 m, Verviers EUR 5.83 m, Chaudfontaine EUR 5.71 m, Esneux EUR 5.61 m, Trooz EUR 5.48 m, Pepinster EUR 5.05 m, Theux EUR 5.01 m, Rochefort EUR 4.86 m, Limbourg EUR 4.67 m, Eupen EUR 0.59 m); **3,521 people rehoused**; 600,000+ hot meals; EUR 550 drying premium to >9,500 households; 1,050 dehumidifiers to the 38 worst-hit communes.

> ⚠️ **Death-toll discrepancy to flag.** **39** is the official Walloon Government/police figure for **Wallonia** (July 2022). **41 deaths + 2 missing in Belgium** was reported by VRT on 27 July 2021 and **41** is the figure in the Wikipedia "2021 European floods" article and several academic papers (which also give **227 deaths** across the event, incl. 186 in Germany). Use "**39 deaths in Wallonia per the Walloon Government / police; ~41 reported Belgium-wide**" and cite both. ❌ I found no single federal Belgian document reconciling the two.

### Insured losses (Assuralia — Belgian insurance association) ✅/⚠️
- Assuralia press release **30 January 2023**, `https://press.assuralia.be/actualisation-relative-aux-inondations-de-juillet-2021` ✅: insurers disbursed **EUR 2 billion**; total estimated damage **EUR 2.4 billion**; **EUR 1.05 billion** to be reimbursed over time "par les régions" (the regions). Settlement at 31 Dec 2022: 85% fully indemnified and closed, 12% paid at 80%, 3% still open. Assuralia: the scheme showed the current law to be *"insuffisante et inapplicable"* (insufficient and inapplicable); the release calls for "une solution uniforme", its president regrets the absence of "un régime clair et uniforme pour l'ensemble des régions", and its CEO adds that the 2021 deal is not renewable and that water does not stop at the language border.
- Later Assuralia updates ⚠️ (via RTBF / La Libre, not read at source): **~74,000 claims** (Wallonia 62,440; Flanders 7,902; Brussels 1,404), total **≈EUR 2.3 bn** (Wallonia EUR 2.24 bn, Flanders EUR 38.7 m, Brussels EUR 18.4 m); **>98.3% of files fully settled** five years on (July 2026). The 4-year update page `https://press.assuralia.be/quatre-ans-apres-les-inondations--chiffres-actualises-et-lecons-pour-lavenir` returned **404** ❌ — find the live Assuralia URL before citing these in print.
- **Cross-check:** EIOPA's own CATDAT-based series bumped Belgium's *insured* flood losses from EUR 2,139 m (2022–2024 dashboards) to **EUR 2,739 m** in the 2025 dashboard — consistent with the Assuralia + Walloon Region combined payout working its way into the data.

### Walloon Commission d'enquête parlementaire — conclusions ✅ full report read
- **Doc. 894 (2021-2022) — N° 1, Parlement wallon, 24 March 2022**: *"Rapport de la Commission d'enquête parlementaire chargée d'examiner les causes et d'évaluer la gestion des inondations de juillet 2021 en Wallonie"*, rapporteurs **M. Bierin and Mme Schyns**. PDF: `https://nautilus.parlement-wallon.be/Archives/2021_2022/RAPPORT/894_1.pdf` (94 pp., ~20 MB). Established by resolution of **1 September 2021** (Doc. 662 (2020-2021) N° 4).
- **161 numbered recommendations** ✅ (verified by parsing to recommendation #161; media report "161, or 187 counting sub-recommendations"). **Adopted by 8 votes with 1 abstention**; endorsed by the plenary on **31 March 2022**. The Commission asked the Parliament's President to transmit the report to the Chamber of Representatives, the Prime Minister, **the President of the European Commission and the President of the European Council**, because some recommendations address the federal and EU levels. **48+ witnesses** heard (SPW secretary-general, RMI/IRM, SPW Hydrological Management, Centre régional de crise, NCCN, provincial governors, 18 mayors, ULiège academics, dam operators, Civil Protection).
- **Recommendations are organised with "1. PRÉVISIONS ET ALERTES MÉTÉOROLOGIQUES ET HYDROLOGIQUES" first**, then "2. PRÉVENTION DES RISQUES ET GESTION DE CRISE" — warning and forecasting failures are the report's opening finding.

**The single most important finding for an AI flood-risk project** ✅ verbatim from the report, testimony of M. Dierickx, Director of Hydrological Management, SPW Mobilité et Infrastructures:
> *"il confirme qu'à aucun moment durant la période de crise son service ne s'est connecté au service « Map Viewer » de l'EFAS et que l'EFAS n'est d'ailleurs pas utilisé de façon opérationnelle dans les procédures de sa direction, ce système n'étant pas – pour l'administration – estimé assez fiable à ce stade."*
> ("He confirms that at no point during the crisis did his service connect to EFAS's Map Viewer, and that EFAS is in fact not used operationally in his directorate's procedures, this system not being — for the administration — considered reliable enough at this stage.")

**→ This is the brief's core argument: the warning existed and was not consumed. A trust/usability/institutional-integration failure, not a forecasting failure.**

**Documented timeline from the inquiry report** ✅
- **10 July**: EFAS begins issuing notifications (first riverine notification) — this date comes from JRC135679, not from the inquiry report.
- **12 July**: RMI/IRM yellow warning received by the Centre régional de crise (CRC); "all rivers" bulletin and a "holiday camp" message sent; **informal EFAS warning** received by SPW; informal contacts between the Vesdre dam duty engineer and Hydrological Management. RMI activates reserve staff.
- **13 July**: **formal EFAS warning** received; RMI confirms its forecast and issues an **orange** warning for Liège, Namur and Luxembourg provinces; RMI sends GRIB files to SPW indicating a risk of **190 mm** of rain at specific points; Hydrological Management asks the CRC to publish a "high vigilance" communication; CRC puts a public communication online.
- **14 July, 06:00/06:16**: flood alert phase triggered; CRC duty officer runs the "procédure crue" and sends **BE-Alert** phone and e-mail messages to concerned actors and to the communes that had requested CRC services. All available teams mobilised from 08:00.
- **14 July, 09:27**: RMI issues a **red alert** for the whole province of Liège, citing **60–150 litres** of rain. The report records that this *"entraîné des hésitations"* — SPW services did not know whether the figures included rain already fallen; the duty engineer had to phone RMI to learn they were **additional** to prior rainfall.
- **14 July, 12:50 and 13:00**: the **Hoëgne and Chaudfontaine gauging stations stopped responding**, blinding SPW to the situation at those locations.
- **14 July, 14:45**: a further EFAS message on flood and runoff risk in Namur province; 22:10 Walloon Brabant placed on orange.
- **15 July, 07:00**: Monsin dam meeting, including risk of a crane collapse and rising water at the **Tihange nuclear plant**. **16 July**: recession begins.
- RMI's forecaster testified that **derogating from the 12-hour lead time** before a red alert is possible but risks false alarms.

**What the Commission concluded / recommended on warning systems and preparedness** ✅ verbatim-sourced (Section VII, recommendations 1–19 and the "culture du risque" block):
- *On EFAS (rec. 1):* commit Wallonia resolutely to the EFAS network; **integrate all EFAS tools — formal and informal "flood" and "flash flood" notifications and the Map Viewer — into SPW procedures**; comply with the EFAS access conditions **signed by the Walloon Region on 23 February 2015** by regularly giving EFAS feedback on forecast quality; attend the annual meetings and training; share rain-gauge and other measurement data with the EFAS Dissemination Centre.
- *On Copernicus EMS (rec. 2):* reduce the delay in delivering satellite-derived imagery to competent authorities.
- *On RMI/IRM (rec. 3–5):* strengthen the SPW–RMI partnership; finer-mesh forecasting with better prediction and integration of **convective** rainfall; mutual knowledge and **interoperability** of tools and data; have RMI communicate the **exact list of communes** covered by each warning; create an RMI product analysing forecast impact on **sub-basins containing a dam**; **(rec. 4) allow yellow/orange/red alerts to be issued without waiting the standard 48 h / 24 h / 12 h** where exceptional events are possible; align weather forecast models with prospective climate models.
- *On hydrological forecasting (rec. 6–14):* integrate **ECMWF** forecasts and non-navigable watercourse data (**Aqualim**) into the **HydroMax** model; raise modelling capacity using a larger risk factor for climate extremes; bring **all** watercourses and the **runoff** problem into the alarm/alert system; operationalise **Walhydro** as a single flood database merging **Aqualim** and **Wacondah** into one metrological network; open all RMI and EFAS products to SPW and other regional authorities; **develop alarm models specifically for flash floods**; **apply Open Data Directive (EU) 2019/1024 to Walhydro and HydroMax data**, making them accessible to managers, public authorities and, as far as possible, **citizens**; study runoff flood risk in detail (preferential flow corridors). **Clarify and publish the terminology of pre-alert/alert codes and thresholds**, and consider launching pre-alerts/alerts **on meteorological forecasts alone, without waiting for hydrological forecast results** (rec. 7). Send communications that are *"compréhensible, signifiante et directement exploitable"* (understandable, meaningful and directly actionable) to regional and municipal authorities **and to the population** (rec. 8); build a standard template for bulletins and pre-alert/alert messages with the CRC-W and the UVCW (rec. 9); model sub-basins more precisely, including the impact of dam releases (rec. 10); **harden and widen the range of the hydrometric gauging stations** so they do not fail at extremes (rec. 11); improve cooperation with the Brussels and Flemish hydrological services and neighbouring countries, with attention to dams (rec. 12); put popularised hydrological data into mainstream public weather bulletins (rec. 13); and **(rec. 14) strengthen the preliminary flood risk assessment capacity required by Article 4 of Directive 2007/60/EC**, taking account of past floods with significant adverse impacts.
- *On the monitoring centre (rec. 15–19):* finalise **PEREX 4.0**; define a phase triggering operational standby for rivers and dams; integrate hydrological pre-alert/alert threshold monitoring into PEREX 4.0; ensure real-time visual monitoring of sensitive hydrological sites, dams included.
- *On risk culture (rec. 20+):* factor worsening climate extremes into all public infrastructure procedures; **train more public officials in emergency planning and crisis management**; build interaction between emergency-planning coordinators (PLANU), spatial-planning advisers (CATU) and delegated officials; cooperate with the **Federal Centre of Excellence for Climate** and **OCAM Climat** on climate risk expertise for regional competences.
- Witness-stage recommendations worth quoting ⚠️ (Section V, attributed to named witnesses rather than adopted as Commission findings): give the CRC a **statutory (decree) mandate** defining its missions and role; clarify the federal/regional division of competences; **"créer un outil capable d'interpréter les données météorologiques qui sont diffusées"** (create a tool able to interpret the meteorological data being broadcast) — SPW Secretary-General; set up a **natural-catastrophe risk centre** staffed by specialists to advise local authorities, and attach an **explanatory note to meteorological data** so recipients understand it — RMI; **stop building in flood-prone areas** and revise the flood-zone mapping — ULiège (Pirotton, Fettweis).

**Independent evaluations also published** ✅ (listed at `https://www.wallonie.be/fr/inondations-de-juillet-2021-rapports-etudes-projets-subventions`): the **Stucky** (Swiss) independent analysis of hydraulic/dam management (two volumes: factual chronology plus 70+ citizen testimonies, and recommendations); the Special Commissariat for Reconstruction's balance sheet; the **Vesdre basin strategic scheme (25 communes)**; redevelopment studies for the 9 worst-hit municipalities; planning support for 31 communes; **EUR 71.2 m** of municipal resilience subsidies; and ~880 km of resilient bank reconstruction along the Vesdre and tributaries.

### JRC/Copernicus evaluation of EFAS performance ✅ read in full
*CEMS EFAS Technical Assessment Report*, **JRC135679**, European Commission, Ispra, **2023**; authors Grimaldi, Thiemig, Pechlivanidis, Sprokkereef, Harrigan, Mazzetti, Prudhomme, Ziese, Schirmeister, Carpintero Salvo, Márquez Arroyo et al. `https://european-flood.emergency.copernicus.eu/sites/default/files/2023-12/JRC135679_CEMS_EFAS_DetailedAssessmentReport_RhineMeuseFloodsJuly2021_FINAL.pdf`
- *"During the event, EFAS issued **25 notifications: 5 Formal Flood Notifications, 6 Informal Flood Notifications, and 14 Flash Flood Notifications**."*
- First riverine notification: **Saturday 10 July**. First flash-flood notifications: **Monday 12 July**. *"The flash flood notifications for the hard-hit locations in both Germany and Belgium (e.g., the **Vesdre** and the Ahr basins) were issued **just before midday on Tuesday, July 13**."* Peak discharges were recorded **14–16 July** → roughly **1.5–2 days of lead time** for the Vesdre flash-flood warning, and **~4 days** for the first riverine notification.
- Formal notifications (strict criteria, ≥48 h lead time) were issued for the **Rhine, Ourthe, Rur/Roer and Moselle**; criteria **could not be met** for the **Meuse, Sauer, Ruhr and Sambre**; **informal** notifications filled the gap on the Meuse and Sauer; **no notification at all could be issued for the Sambre** *"because the event was not detected by the EFAS forecasts"*; one informal notification was a **false alarm** (Nahe).
- Verification: in **33 of 46 instances** the formal-notification criteria agreed with the EFAS water-balance simulation; the 13 misses were due to *"the flashy nature of the events and … inconsistencies in the forecasts."* EFAS simulated discharge peaks were *"generally larger and earlier than the observations."* Precipitation forecasts were *"highly uncertain and affected by underestimation error."*
- Overall: *"an overall good performance of the system"*, with improvement actions on model set-up, notification criteria and **communication protocol** — *"the analysis of this report highlighted ways to further improve the **effectiveness and clarity** of the EFAS notifications to facilitate the **uptake** of the early warnings by the regional and national authorities."*
- ⚠️ Two explicit caveats from the report, which must be honoured if it is quoted: it is a *service* performance assessment only, *"the conclusions and recommendations of this report should not be used for any other purpose"*, and because it uses data unavailable at the time, *"the report cannot and should not be used to assess any flood event management decision taken at the time."*

**Supporting academic evidence on the warning gap** ⚠️ (preprint, not peer-reviewed — flag as such): *"Learning from the past to inform flood risk management: Analysis of public survey data in Belgium on flood early warning and response during the July 2021 flood"*, EGUsphere preprint **egusphere-2025-6376**, `https://egusphere.copernicus.org/preprints/2026/egusphere-2025-6376/` — reports that **33% of Walloon respondents received no warning at all** and **56% did not know how to respond effectively**. Also relevant and peer-reviewed: *"Performance of the flood warning system in Germany in July 2021"*, NHESS 23, 973 (2023), `https://nhess.copernicus.org/articles/23/973/2023/`; *"Signals without action: a value chain analysis of Luxembourg's 2021 flood disaster"*, NHESS 26, 343 (2026), `https://nhess.copernicus.org/articles/26/343/2026/`; *"Quantitative rainfall analysis of the 2021 mid-July flood event in Belgium"*, HESS 27, 3169 (2023), `https://hess.copernicus.org/articles/27/3169/2023/`.

---

## 7. EU AI Act (Regulation (EU) 2024/1689) — what actually applies to a public-authority flood-risk AI system

**Sources** ✅
- Original: **Regulation (EU) 2024/1689 of 13 June 2024**, OJ L, 12.7.2024. `https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng`
- **Amended** by **Regulation (EU) 2026/1744 of 8 July 2026** ("Digital Omnibus on AI"), OJ L 2026/1744, **24.7.2026**, in force **27 July 2026**. `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ%3AL_202601744` ✅ read
- Consolidated text: `https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng`
- Commission AI Act page (page dated 3 August 2026) ✅ `https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai`
- Article/annex texts also checked against `https://artificialintelligenceact.eu/annex/3/`, `/article/50/`, `/article/27/` ⚠️ (reliable unofficial mirror — re-verify any quoted wording against EUR-Lex before publication)

> **Note for the team:** the Digital Omnibus amendment is **after my May 2026 knowledge cutoff** and I verified it in this session. It amends **42 articles and 3 annexes**. Do not rely on pre-July-2026 AI Act commentary.

### Is flood risk assessment high-risk under Annex III? **No — not as such.** Be precise here.
Annex III headings (verbatim) ✅: 1. **Biometrics** · 2. **Critical infrastructure** · 3. **Education and vocational training** · 4. **Employment, workers' management and access to self-employment** · 5. **Access to and enjoyment of essential private services and essential public services and benefits** · 6. **Law enforcement** · 7. **Migration, asylum and border control management** · 8. **Administration of justice and democratic processes**

- **Annex III point 2 in full** (verbatim) ✅: *"AI systems intended to be used as safety components in the management and operation of critical digital infrastructure, road traffic, or in the supply of water, gas, heating or electricity."*
  - **Flood risk assessment, flood hazard/risk mapping and flood forecasting are not listed.** Point 2 is limited to **safety components** in the **operation of** the named infrastructures. A flood model could fall in only if it is a *safety component* in, say, the operation of **water supply** — a narrow and arguable reading. **Do not claim flood risk assessment is high-risk under point 2.**
- **Annex III point 5** (verbatim sub-points) ✅: (a) evaluating eligibility for **essential public assistance benefits and services, including healthcare**, and granting/reducing/revoking/reclaiming them; (b) **creditworthiness / credit scoring**; (c) **risk assessment and pricing in life and health insurance**; (d) *"AI systems intended to evaluate and classify **emergency calls** by natural persons or to be used to **dispatch, or to establish priority in the dispatching of, emergency first response services**, including by police, firefighters and medical aid, as well as of emergency healthcare patient triage systems."*
  - **5(d) is the one genuinely live path to high-risk for a flood project.** If the system triages 112 calls or prioritises the dispatch of fire/rescue/medical units during a flood, it **is** Annex III high-risk. A system that only produces hazard maps, risk scores, or warnings for officials is **not** caught by 5(d).
  - **5(c)** matters only for a flood-insurance pricing angle, and even then note it is **life and health** insurance — **property/flood insurance pricing is not in Annex III**.
  - Honest framing for the brief: *"A flood hazard-mapping or forecasting tool for a public authority is, on the face of Annex III, not a high-risk AI system. It becomes high-risk if it crosses into emergency-call triage or first-responder dispatch prioritisation (Annex III, point 5(d)), or if it is a safety component of a product covered by Annex I. The honest position is therefore: design to high-risk standards voluntarily, and treat Article 6(2)/Annex III as a boundary the project should not drift across unexamined."*
- **Article 6(3) derogation** ⚠️ (text not re-read verbatim this session): even where an Annex III use case is matched, a system is **not** high-risk if it does not pose a significant risk of harm to health, safety or fundamental rights, i.e. where it performs only a **narrow procedural task**, **improves the result of a previously completed human activity**, **detects decision-making patterns or deviations** without replacing or influencing the human assessment without proper human review, or performs a **preparatory task** to an assessment. A provider relying on this must **document the assessment** and still **register** the system in the EU database. **Verify the exact wording on EUR-Lex before citing.**

### What *does* bite for a public authority
- **Article 50 — transparency obligations** ✅ (paraphrased from the article; verify wording before quoting)
  - **50(1)** Providers must ensure AI systems **intended to interact directly with natural persons** are designed so those persons **are informed that they are interacting with an AI system**, unless it is obvious to a reasonably well-informed person. → **A public-facing flood chatbot or citizen-facing Q&A assistant is squarely in scope.**
  - **50(2)** Providers of systems generating **synthetic audio, image, video or text** must **mark outputs in a machine-readable format** as artificially generated or manipulated, with solutions that are effective, interoperable, robust and reliable so far as technically feasible. Exemptions for assistive editing and systems not substantially altering input data.
  - **50(3)** Deployers of **emotion recognition** or **biometric categorisation** systems must inform the exposed persons and process personal data per the GDPR. → Normally not relevant to a flood tool; relevant if there is any crowd/victim-detection component.
  - **50(4)** Deployers generating or manipulating **deep fakes** must disclose that the content is artificially generated; and deployers who generate or manipulate **text published to inform the public on matters of public interest** must disclose that it is AI-generated **unless the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility**. → **This is the provision to cite for AI-drafted flood bulletins, risk summaries or public advisories.** The human-editorial-responsibility carve-out is the practical compliance route, and it is worth stating in the brief that this is exactly what the Walloon Commission demanded institutionally anyway (rec. 8–9: understandable, directly actionable messages produced with the CRC and UVCW).
  - **50(5)** The information must be given *"in a clear and distinguishable manner at the latest at the time of the first interaction or exposure"* and must meet accessibility requirements.
  - **Scope caveat for precision:** Article 50 obligations are **use-case triggered**, not actor-triggered. A flood-risk tool that only computes and displays maps and numbers to officials, with no direct human interaction and no generated content, triggers **none** of Article 50. Do not overclaim that Article 50 "applies to any flood AI".
- **Article 27 — Fundamental Rights Impact Assessment (FRIA)** ✅ — this is the most relevant public-authority obligation. Verbatim opening: *"Prior to deploying a high-risk AI system … deployers that are **bodies governed by public law**, or are **private entities providing public services** … shall perform an assessment of the impact on fundamental rights"*. Required content (a)–(f): (a) description of the deployer's processes in which the system will be used for its intended purpose; (b) the timeframe and frequency of intended use; (c) the categories of natural persons and groups likely to be affected in the specific context; (d) the specific risks of harm likely to affect those persons/groups, taking the provider's information into account; (e) a description of the implementation of human oversight measures, per the instructions for use; (f) the measures to be taken if those risks materialise, including internal governance and complaint mechanisms. **Conditional on the system being high-risk** — so for a non-Annex-III flood tool the FRIA is a **voluntary best-practice framework**, and that is a strong, honest pitch for the hackathon: *we ran an Article 27-shaped assessment even though Article 27 does not compel us*.
- Also relevant, and worth naming without over-detailing: **Art. 4** AI literacy (in force since 2 Feb 2025, applies to providers *and* deployers); **Art. 5** prohibited practices (in force since 2 Feb 2025); **Art. 26** deployer obligations for high-risk systems (use per instructions, human oversight, input-data relevance, logging, informing affected persons); **Art. 49(3)** registration of high-risk systems by public-authority deployers in the EU database; **Art. 86** right to an explanation of individual decision-making; **Art. 25** when a deployer becomes a provider (e.g. by substantially modifying a system or putting its own name on it — a real risk if the team fine-tunes a model); **Art. 2** scope exclusions, including **scientific research and development** and **personal non-professional use** — a hackathon prototype may well sit in the R&D exclusion, which is itself worth stating accurately rather than claiming compliance theatre.

### Application dates (post-Omnibus) ✅ confirmed from both Reg. 2026/1744 and the Commission's own page
| Obligation | Applies from |
|---|---|
| Prohibited practices (Art. 5), AI literacy (Art. 4), general provisions | **2 February 2025** |
| GPAI model rules, governance, notifying authorities, penalties | **2 August 2025** |
| General application of the Regulation incl. **Article 50 transparency** | **2 August 2026** (with a 4-month transitional grace for marking obligations on systems placed on the market before that date) |
| **High-risk, stand-alone Annex III systems** (Chapter III Sections 1–3, Art. 6(2)) | **2 December 2027** — *deferred from 2 August 2026/2027* |
| **High-risk systems in Annex I regulated products** (Art. 6(1)) | **2 August 2028** — *deferred from 2 August 2027* |

- Reg. 2026/1744 also **did not** substantively rewrite Annex III of the AI Act (its Annex III delegated-act power concerns Regulation (EU) 2023/1230 on machinery), and it **did not** move the Article 50 application date (it only adds the four-month marking grace in the table above, to 2 December 2026, for Art. 50(2) systems already on the market). It additionally prohibits AI systems generating non-consensual intimate imagery and CSAM (those new Art. 5 prohibitions apply from 2 December 2026, not 2 February 2025), and simplifies documentation duties for SMEs and small mid-caps.
- **The line for the brief:** *as of the hackathon, the AI Act's transparency rules are already in force (since 2 August 2026) and the high-risk regime is not (Annex III: 2 December 2027). That gap is a design opportunity, not an excuse.*

---

## 8. HLEG Ethics Guidelines for Trustworthy AI — the 7 key requirements

**Source** ✅ `https://digital-strategy.ec.europa.eu/en/library/ethics-guidelines-trustworthy-ai`
- *Ethics Guidelines for Trustworthy AI*, by the **High-Level Expert Group on Artificial Intelligence (AI HLEG)**, an independent expert group set up by the European Commission; published **8 April 2019**. (Companion: the **Assessment List for Trustworthy AI (ALTAI)**, July 2020, `https://digital-strategy.ec.europa.eu/en/library/assessment-list-trustworthy-artificial-intelligence-altai-self-assessment` ⚠️ URL not fetched this session.)
- Trustworthy AI, per the Guidelines, should be **lawful, ethical and robust**, and rest on four principles (respect for human autonomy, prevention of harm, fairness, explicability), operationalised through **7 key requirements**:

1. **Human agency and oversight**
2. **Technical robustness and safety**
3. **Privacy and data governance**
4. **Transparency**
5. **Diversity, non-discrimination and fairness**
6. **Societal and environmental well-being**
7. **Accountability**

✅ Names verified against the Commission page. Quotable gloss on requirement 1 ✅: AI systems should *"empower human beings, allowing them to make informed decisions and fostering their fundamental rights"*, with appropriate human oversight mechanisms.

**Why these map cleanly onto the flood case** (argument, not a cited finding): requirement **1 (human agency and oversight)** and **4 (transparency)** are precisely what failed in July 2021 — a warning system existed, and the humans in the loop did not trust it, did not use it, and could not interpret its numbers (the "60–150 litres: on top of, or including, what already fell?" episode). Requirement **6** carries the climate-adaptation dimension. The Guidelines are **non-binding**, and the brief should say so; their value is as the design vocabulary that the AI Act later made law in Articles 13, 14, 26 and 27.

---

## Cross-cutting synthesis for the brief

1. **The policy machinery exists and is on a clock.** Floods Directive third cycle: updated maps were due 22 Dec 2025, third-generation FRMPs are due **22 Dec 2027**. The European Climate Adaptation Plan / integrated climate-resilience framework is expected ~**20 October 2026**, days before the hackathon.
2. **The money case is settled.** Floods are **47% of EUR 822 bn** of EU weather/climate losses 1980–2024 (EEA, 14 Oct 2025, 2024 prices) — the largest single category — and **25% of all those losses fell in 2021–2024 alone**. Hydrological losses are only **~15% insured**.
3. **The failure mode is uptake, not prediction.** EFAS issued **25 notifications** from **10 July 2021**, including flash-flood notifications for the **Vesdre** before midday on **13 July**; the Walloon hydrological service *"at no point connected to the EFAS Map Viewer"* and did not use EFAS operationally, judging it insufficiently reliable (Doc. 894, 24 March 2022). **33% of Walloon residents received no warning; 56% did not know how to respond** (preprint). The Commission d'enquête's **161 recommendations open with forecasting and alerting**, and its asks are interpretability, interoperability, plain-language messaging, open data and faster alert triggers — i.e. a *decision-support and trust* problem, which is where an AI system can legitimately add value.
4. **Belgium's insurance gap is about capacity, not coverage.** Near-universal mandatory flood cover attached to fire insurance gives Belgium a **low current EIOPA flood score (1.5)** and a total score of **6** (vs EEA 5.5, Italy/Greece 12) — yet **78% of Belgium's 1980–2024 flood losses were uninsured**, and in 2021 the statutory cap would have paid policyholders only **20%** of assessed damage until the Walloon Region put up **EUR 1 bn** (final split: insurers 41% / Region 59%). Europe-wide, **Italy and Germany flood alone account for 25% of all uninsured nat-cat losses**.
5. **The AI governance position must be precise, not maximalist.** Flood risk assessment is **not** an Annex III high-risk use case; it crosses into high-risk only via **5(d)** (emergency-call triage / first-responder dispatch prioritisation) or as an Annex I safety component. **Article 50** bites only on direct human interaction, synthetic content, and AI-generated public-interest text (with the human-editorial-responsibility carve-out). **Article 27 FRIA** binds public bodies only for high-risk systems. The defensible stance: adopt the **HLEG 7 requirements** and an **Article 27-shaped FRIA voluntarily**, and state plainly which obligations are legally triggered and which are not.

---

## Open items and flags

| # | Item | Status |
|---|---|---|
| 1 | Third-cycle Floods Directive dates (22 Dec 2024 / 2025 / 2027) | ⚠️ Arithmetic from Art. 14 + national implementing sources; no single Commission page states all three |
| 2 | Flood damage total: EUR 170 bn (EUCRA 2024) vs ≈EUR 386 bn (47% of EUR 822 bn, EEA Oct 2025) | ⚠️ Different vintages/price bases — use the EEA 2025 figure, cite with date, do not merge |
| 3 | UNDRR canonical URL and overview page | ✅ Both return HTTP 200 to a scripted fetch (6 Oct 2026) — no bot block — and the landing page is on disk at 51,144 B with `error: null`. Verbatim text is still taken from the framework PDF, because the canonical URL is a publication landing page rather than the text; UNDRR's own `/media/16176/download` link is the one that answers 200 with a JS stub instead of the PDF |
| 4 | Death toll: 39 (Wallonia, Walloon Govt/police) vs 41 + 2 missing (Belgium, VRT/academic) | ⚠️ Report both; no reconciling federal source found |
| 5 | rescEU has no flood-specific EU-owned reserve; flood modules (HCP, flood containment, flood rescue) sit in the European Civil Protection Pool | ⚠️/❌ Module names not verified against the UCPM implementing decision annex |
| 6 | Assuralia 4-year update URL returns 404 | ❌ Later Assuralia figures (~74,000 claims, ~EUR 2.3 bn, 98.3% settled) are press-sourced only |
| 7 | European Climate Adaptation Plan / integrated climate-resilience framework | ❌ Not yet on EUR-Lex; "expected 20 October 2026" is press/EPRS-sourced — re-check on the day |
| 8 | AI Act Art. 6(3), Art. 50 and Art. 27 wording | ⚠️ Read via artificialintelligenceact.eu mirror; EUR-Lex HTML truncated on fetch. Re-verify verbatim quotes against the consolidated EUR-Lex text before publication |
| 9 | Belgian Insurance Act of 4 April 2014, Art. 123; "simple risks" threshold | ❌ Statutory text not read; figure of ≈EUR 1,445,715 is secondary-sourced and index-linked |
| 10 | EIOPA nutshell says "Seven countries should be closely monitored" then lists eight for flood\* | ⚠️ Inconsistency in EIOPA's own document — quote the list, not the count |
| 11 | ALTAI assessment list URL | ❌ Not fetched this session |
| 12 | EIOPA 2026 dashboard update | ❌ None published as of this research; latest is the 2025 light update (EIOPA-BoS-25/564, 10 Nov 2025; page last updated 5 Dec 2025) |

### Recommended RAG corpus (12 entries, 15 documents, all URL-verified above)
Directive 2007/60/EC · Commission Recommendation 2023/C 56/01 (Union disaster resilience goals) · Decision 1313/2013/EU (UCPM) · COM(2021) 82 (Adaptation Strategy) · COM(2025) 280 (Water Resilience Strategy) · EEA Report 01/2024 (EUCRA) + EEA economic-losses indicator (14 Oct 2025) · EIOPA-BoS-25/564 + the dashboard `.xlsx` · Sendai Framework (official PDF) · Walloon Parliament Doc. 894 (2021-2022) N° 1 · JRC135679 (CEMS EFAS assessment of the July 2021 Rhine/Meuse floods) · Regulation (EU) 2024/1689 consolidated at 2026-07-27 + Regulation (EU) 2026/1744 · HLEG Ethics Guidelines for Trustworthy AI (2019).

The list reads as 12 entries because three of them pair two documents (the two EEA items, the two EIOPA items, and the two AI-Act regulations) — count 15 if you are counting files to fetch. On 6 October 2026 only **six** of the twelve entries were declared in `sources.yaml` — Directive 2007/60/EC, the Sendai Framework, Doc. 894, JRC135679, the HLEG guidelines, and the AI Act pair at half (Regulation (EU) 2024/1689 is declared, Regulation (EU) 2026/1744 is not). Building this corpus therefore means declaring and fetching nine more documents, not two; see the undeclared list at the top of this report. Since 12 October 2026 all nine are declared (the EIOPA spreadsheet as `context`, the EUCRA report as its landing page), and the corpus is complete once `python -m src.fetch` has run — except that the Sendai entry is declared as its landing page, so the official PDF stays the manual download listed at the top, and the spreadsheet never enters the retrieval index.

Note for corpus construction: Doc. 894 and the Walloon Government press release are **French-language**; the Walloon inquiry report is the only source containing the EFAS-non-use finding, so the retrieval pipeline needs to handle FR/EN cross-language retrieval or a translated chunk layer. (This is also a `comparability: cross_language` concern if any of this feeds the Becode comparator repo's dictionary conventions.)

# The docs, and where to start

These pages record what the kit measures, why it is built the way it is, and
what the European AI Challenge 2026 (JRC x FARI, 29-30 October) asks for
(Annex 4): a policy tool, the policy brief in the Annex 6 template and the AI
sheet in the Annex 7 template, sent by 13:30 on Day 2, then a five-minute live
demo, judged equally on evidence, policy usefulness, clarity and responsible
AI use. The brief is a funnel ([`scope.md`](scope.md)): the July 2021 flood in
Belgium, Germany and the Netherlands at the core, the kit's EU-wide findings
as the context. Seventeen Markdown files in this folder, 427.3 KB measured on
2026-10-31, sixteen of them indexed below. Most of that is background written
before the data was frozen; the argument
itself is short, and this page exists so a reader opens it first rather than a
reference of 50 KB or more.

**Twenty minutes:** [`policy_answer.md`](policy_answer.md) (the EU-level
spine: four measured findings, three recommendations with an article, an
addressee and a date; the hackathon case's own three recommendations for Anna
are in the brief, `docs/perso/brief_draft_anna.md`), [`responsible_ai.md`](responsible_ai.md)
(the HLEG grid and what the AI was not allowed to decide) and
[`limitations.md`](limitations.md) (what none of it claims).
[`decisions.md`](decisions.md) is the appendix: the dated record behind every
figure the first three quote.

## What each file holds

Sizes measured on 2026-10-31 with `os.path.getsize`, in KB of 1,024 bytes; they
move with every edit, so re-measure rather than quote.

| Path | Holds | KB |
|---|---|---|
| [`policy_answer.md`](policy_answer.md) | The question the organisers ask, the measured base at RP100 (25,737,004 people exposed in the EU-27), four findings with their caveats, the Directive's calendar, three recommendations with the authority and the date behind each, and what the page does not claim. | 26.9 |
| [`responsible_ai.md`](responsible_ai.md) | The HLEG seven-requirement grid with what the kit can honestly claim under each, licence hygiene, tracing, the usage-log format with the Annex 7 columns, the no-personal-key rule for the event, and the four things AI must not decide. | 10.3 |
| [`decisions.md`](decisions.md) | The short dated record of every change to what a number means, oldest first: one four-line entry each, with the figures before and after. | 34.2 |
| [`limitations.md`](limitations.md) | What the figures cannot say, what was designed and not built, what an authority would still have to do, and the risks accepted to ship in ten days, each bullet pointing at its source. | 32.1 |
| [`technical_deep_dive.md`](technical_deep_dive.md) | How the pipeline works and why: the five CRSs, what the exposure columns mean, why windows are cut on the population grid, the UI contract and the fourteen routes, validation, the July 2021 pipeline, the LLM layer, and the test suite. | 42.4 |
| [`scope.md`](scope.md) | The funnel (July 2021 in BE/DE/NL at the core, Europe as the context), why the context's unit is NUTS3, what that changes about population, boundaries and demographics, the alignment rule, and why Belgium carries the validation. | 12.6 |
| [`strategy.md`](strategy.md) | What would win: the observed satellite flood-depth series most teams will not find, the comparison questions, and the "risk of being unprepared" framing the brief adopts. | 8.3 |
| [`datasets.md`](datasets.md) | Every declared source, verified against the live host: CRS, unit, size, licence and the specific trap each one sets, plus what is on disk and not yet read by any code (the Walloon IDW depth raster). | 53.4 |
| [`geospatial_crash_course.md`](geospatial_crash_course.md) | A ten-minute glossary for the non-GIS teammate, then the ways this project's data returns a plausible wrong number: CRS, non-square cells, units, counts versus densities, zonal statistics, NUTS nesting, IoU. | 31.6 |
| [`policy_context.md`](policy_context.md) | The EU flood-risk policy framework researched for the RAG corpus and the brief: the Floods Directive cycle, Sendai, civil protection, the insurance gap, the July 2021 figures, the AI Act, with a verification flag on every claim and twelve open items. | 64.4 |
| [`policy_craft.md`](policy_craft.md) | How a brief, a demo and a decision-maker's map are judged: the Annex 4 criteria, BLUF, the recommendation sentence template, the skeleton mapped onto the Annex 6 headings, uncertainty wording, and why teams lose. | 55.3 |
| [`workflow.md`](workflow.md) | Why the brief pipeline is a fixed five-node graph and not an agent: the four guards, the approval gate, idempotent fetching, and verification done in Python rather than by a model. | 7.9 |
| [`roles.md`](roles.md) | The integrator's five hats (Solvay strategist and economist, then business analyst, data analyst, AI engineer; who is in the room), the Annex 5 roles (two Coders, two Researchers, two Communicators) with what each owns and hands over, when they meet, and the two rules that save the deliverable. | 11.7 |
| [`plan.md`](plan.md) | The plan for the two days: the event page, what to have done before the doors open (the download, the Risk Data Hub token, the vocabulary), the dress rehearsal on a region nobody prepared, and what not to do. | 3.3 |
| [`README.md`](README.md) | This index. | 6.9 |
| [`power_bi.md`](power_bi.md) | The Power BI project (`bi/FloodToPolicy.pbip`): how to open it, the cover and eight story pages and the claim each makes, drill-down and drill-through, the two-table model, the measures and the rule each enforces, the theme, the map to add by hand, how the PBIR files are generated and validated. | 21.4 |

## Full reading order

1. [`policy_answer.md`](policy_answer.md): the whole argument, with the
   numbers, in one sitting.
2. [`limitations.md`](limitations.md): what those numbers do not support,
   before any of them is repeated.
3. [`responsible_ai.md`](responsible_ai.md) then
   the team's AI log: the reflection and its evidence.
4. [`scope.md`](scope.md) and [`strategy.md`](strategy.md): the funnel, why
   the context is Europe at NUTS3, and why the brief asks about preparation rather than water.
5. [`technical_deep_dive.md`](technical_deep_dive.md): what each column means
   and how the pipeline keeps the headline additive.
6. [`workflow.md`](workflow.md): why there is a human gate and no agent.
7. [`datasets.md`](datasets.md) and
   [`geospatial_crash_course.md`](geospatial_crash_course.md): the reference
   half, read when a source or a number needs checking.
8. [`policy_context.md`](policy_context.md),
   [`policy_craft.md`](policy_craft.md), [`roles.md`](roles.md),
   [`plan.md`](plan.md): the preparation material, written
   before the freeze.

When a figure here and a figure in the code disagree, the code and
`config/sources.yaml` are right. [`decisions.md`](decisions.md) is the dated
record of every such change, and [`limitations.md`](limitations.md) is what the
kit does not claim.

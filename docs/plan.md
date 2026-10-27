# Preparation plan — 23 days

**Today: Tuesday 6 October 2026. Day 1: Thursday 29 October, 09:00 at FARI.
Day 2: Friday 30 October, until 18:00 at JRC.**

Daylight saving ends Sunday 25 October; 09:00 CET on the 29th is 09:00 Brussels
time, so nothing to adjust.

## Do today, before anything else

1. **Register.** 60 places, free, and applications are open now. Registration and
   programme: <https://joint-research-centre.ec.europa.eu/events/european-ai-challenge-2026-data-policy-2026-10-29_en>
   — the same URL `config/sources.yaml` declares as `event_page`, verified HTTP 200
   on 6 October 2026. The shorter `/jrc-events/european-ai-challenge-2026-data-policy`
   form returns 404; the path segment is `/events/` and the date suffix is part of
   the slug.
2. **Settle your eligibility in writing.** The call targets students of Belgian
   universities, *hautes écoles* and *hogescholen*. BeCode is a bootcamp, not a
   *haute école*. Write to **info@fari.brussels** today, state "BeCode AI & Data
   Science / GenAI Developer track", and ask them to confirm. Do not assume, and
   do not wait — if the answer is no you want three weeks to find another route
   (a partner university team, for instance).
3. **Ask about prepared code.** Same email: ask whether arriving with a generic
   toolkit is acceptable. Almost every hackathon allows it; getting it in writing
   removes any doubt, and asking makes a good first impression.

## The calendar

| Week | Goal | Done when |
|---|---|---|
| **Mon 5 → Sun 11** | Register. Learn the domain: Floods Directive, Sendai, Hazard×Exposure×Vulnerability. Download every dataset — **85 files; the 84 declared on 25 October measured ≈6.96 GiB on disk that day**. Get `geopandas`/`rasterio` under your fingers. | You can produce one map of exposed population on the Vesdre valley, 2021 |
| **Mon 12 → Sun 18** | The kit: exposure pipeline, vulnerability index, Streamlit map, tests, CI. | `pytest` green, `streamlit run` shows a real map |
| **Mon 19 → Sun 25** | GenAI layer: grounded RAG over the policy corpus, brief template, responsible-AI checklist, deploy. **All downloads finished.** | App online, brief template filled with a dry-run result |
| **Mon 26 → Wed 28** | **Full dress rehearsal**: an 8-hour solo hackathon on a *different* region (Valencia DANA 2024, or Emilia-Romagna 2023). Rehearse the demo. Rest Wednesday evening. | A timed five-minute demo of the policy tool you can deliver without notes (Annex 4) |

## Week 1 in detail (5–11 October)

**Domain first, code second.** You cannot frame a recommendation in a field whose
vocabulary you do not have.

- Read `docs/policy_context.md` end to end. Know what a *return period* is, what
  the three stages of the Floods Directive are, and what happened in Wallonia in
  July 2021.
- Learn the vocabulary that will be in the room: *aléa* (hazard), *enjeux*
  (exposed assets), *vulnérabilité*, *période de retour*, *zone d'expansion de
  crue*, *ruissellement* (surface runoff, as opposed to river overflow).

**Then the data.** Follow `docs/datasets.md`. Target for the end of the week:
one PNG showing population exposed to a 100-year flood in the Vesdre valley,
produced by `src/exposure.py`, with the number written on it. The valley sits
inside the July 2021 core the case is about; the European NUTS3 work is the
context around it ([`scope.md`](scope.md)).

**The download, measured.** `python -m src.fetch` is 85 files — 57
geodata downloads, 25 policy-corpus scrapes and 3 context scrapes (counted
2026-10-27); it skips the `geodata` section's 19 runtime API calls, which store
nothing, and the 35 files of its six `folder` entries: the 30 HERA files, which
`scripts/fetch_hera.py` fetches, and the five `challenge_*` folders of the
organisers' bucket, which `scripts/event_2021.py` reads. The 84 files declared on
25 October measured ≈6.96 GiB on disk that day (the 85th,
`natural_earth_countries`, adds 4.9 MB): the
nine return periods alone are 2.61 GiB, and six `download` entries expand to several files
each, so the printed count is files rather than declared sources. Start it once
and leave it; it is idempotent, so a dropped connection costs only the files that
are actually missing. Do not expect `/vsicurl/` to save you the download — it
pays off for a country window (2.4 MiB for Belgium on RP100) and collapses at EU
scale (35,525 tiles, 56% of the file, in tens of thousands of requests). The counts are `src.fetch.expand()`
over `sources.yaml` as it stood on 27 October 2026 and the bytes the files
measured on disk on 25 October — every entry added later moves
them, so re-derive rather than quoting this line.

**One account to open this week.** The JRC Risk Data Hub needs an EU Login
account, and its bearer token lasts 10 hours — so the account is created now and
the *token* is refreshed on the morning of the event. Fill the response cache
(`data/processed/rdh_cache/`) the day before, never live in front of a jury.

**The trap to avoid this week:** spending five days making the pipeline elegant.
It needs to be *correct* and *fast to re-point at another region*, because on the
day you will be handed a scenario you did not choose.

## Week 4: why the dress rehearsal matters most

Do the rehearsal on a region you have **not** prepared. The entire value of the
exercise is discovering which parts of your kit are secretly hard-coded to
Belgium. Everything that breaks on Valencia would have broken on day 1 of the
real event.

Timebox it exactly like the real thing: 8 hours, then a brief and a demo. Record
the demo on your phone and watch it once. It is unpleasant and it is the single
highest-return hour of the whole preparation.

## What to deliberately NOT do

- **No model training.** Nobody is asking for a flood prediction model, and you
  cannot validate one in two days. Analysis, not prediction.
- **No scraping on the day.** Corpus and rasters are collected before the 25th.
- **No dependency on a paid API** that might rate-limit you in front of a jury.
  Have a local fallback (Ollama) for the LLM layer.

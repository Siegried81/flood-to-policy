# Plan for the two days

**Day 1: Thursday 29 October, 09:00 at FARI.
Day 2: Friday 30 October, until 18:00 at JRC.**

Daylight saving ends Sunday 25 October; 09:00 CET on the 29th is 09:00 Brussels
time, so nothing to adjust.

The event page, with registration and programme:
<https://joint-research-centre.ec.europa.eu/events/european-ai-challenge-2026-data-policy-2026-10-29_en>
— the same URL `config/sources.yaml` declares as `event_page`, verified HTTP 200.
The shorter `/jrc-events/european-ai-challenge-2026-data-policy` form returns
404; the path segment is `/events/` and the date suffix is part of the slug.

## Before the doors open

**The download.** `python -m src.fetch` is 85 files — 57 geodata downloads, 25
policy-corpus scrapes and 3 context scrapes (counted 2026-10-27); what it skips
(19 runtime API calls, 35 files under six `folder` entries fetched or read by
`scripts/fetch_hera.py` and `scripts/event_2021.py`), the sizes and why
`/vsicurl/` cannot replace the download at EU scale are in
[`scope.md`](scope.md#hazard-unchanged). The 84 files declared on 25 October
measured ≈6.96 GiB on disk that day. Start it once and leave it; it is
idempotent, so a dropped connection costs only the files that are actually
missing. Re-derive the counts rather than quoting this line: every entry added
to `sources.yaml` moves them.

**The Risk Data Hub token.** The JRC Risk Data Hub needs an EU Login account,
and its bearer token lasts 10 hours — so the *token* is refreshed on the morning
of the event. Fill the response cache (`data/processed/rdh_cache/`) the day
before, never live in front of a jury.

**The vocabulary that will be in the room:** *aléa* (hazard), *enjeux*
(exposed assets), *vulnérabilité*, *période de retour*, *zone d'expansion de
crue*, *ruissellement* (surface runoff, as opposed to river overflow). Know what
a *return period* is, what the three stages of the Floods Directive are
([`policy_context.md`](policy_context.md)), and what happened in Wallonia in
July 2021.

**The trap to avoid:** spending the time making the pipeline elegant. It needs
to be *correct* and *fast to re-point at another region*, because on the day you
will be handed a scenario you did not choose.

<a id="week-4-why-the-dress-rehearsal-matters-most"></a>
## Why the dress rehearsal matters most

Do the rehearsal on a region you have **not** prepared (Valencia DANA 2024, or
Emilia-Romagna 2023). The entire value of the exercise is discovering which
parts of your kit are secretly hard-coded to Belgium. Everything that breaks on
Valencia would have broken on day 1 of the real event.

Timebox it exactly like the real thing: 8 hours, then a brief and a demo. Record
the demo on your phone and watch it once: the goal is a timed five-minute demo
of the policy tool you can deliver without notes (Annex 4). It is unpleasant and
it is the single highest-return hour before the event.

## What to deliberately NOT do

- **No model training.** Nobody is asking for a flood prediction model, and you
  cannot validate one in two days. Analysis, not prediction.
- **No scraping on the day.** Corpus and rasters are collected before the 25th.
- **No dependency on a paid API** that might rate-limit you in front of a jury.
  Have a local fallback (Ollama) for the LLM layer.

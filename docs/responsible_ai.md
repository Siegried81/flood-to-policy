# The responsible-AI deliverable

One of the four scored outputs is a reflection on the responsible use of AI in
your workflow. Most teams will write three vague sentences about bias at 17:00 on
Friday. This is the cheapest place to stand out, because it can be prepared in
advance and filled in as you work.

## Use the jury's own framework

FARI co-organises the event, and its manifesto commits explicitly to the **HLEG
Ethics Guidelines for Trustworthy AI** — seven key requirements. Structuring the
section as that grid means the jury recognises its own vocabulary.

The seven requirements, in the manifesto's own wording (verify the exact wording
against the source before the event — see `config/sources.yaml`; the HLEG page
itself names the sixth "Societal and environmental well-being"):

1. Human agency and oversight
2. Technical robustness and safety
3. Privacy and data governance
4. Transparency
5. Diversity, non-discrimination and fairness
6. Environmental and societal well-being
7. Accountability

## What to write under each, concretely

| Requirement | What you can actually claim, if you do the work |
|---|---|
| Human agency and oversight | Every figure in the brief was traced to its source dataset by a named person. The AI proposed; the team decided the thresholds, the weights and the ranking. |
| Technical robustness | The pipeline has tests; the retrieval layer **refuses** rather than guessing when no source supports an answer. Every draft is checked offline for citations out of range, numbers no passage or table holds, and claim sentences with no citation; an approval with a citation to no source is refused. Say what these checks cannot see: a flipped negation, a claim cited to the wrong passage, a true figure attached to the wrong region. |
| Privacy and data governance | Only aggregated, open data. Population grids, not individuals. No personal data entered any prompt. Each input's licence is recorded and respected — see below. |
| Transparency | Public repo (never linked from the submitted files: Team N only, no names or repo link), AI sheet (Annex 7) compiled from the running AI usage log, and `sources.yaml` carrying a URL and a stated purpose for all <!-- numbers:sources_declared -->82<!-- /numbers --> declared inputs — with a **verification date on <!-- numbers:sources_verified -->61<!-- /numbers -->** and an explicit `licence:` on **<!-- numbers:sources_licensed -->42<!-- /numbers -->** (kept current by `scripts/docs_numbers.py`; the counts are of declared entries, not of the files they expand to) — which is where redistribution is a live question. Five `access: download` entries still carry no `licence:` (`gisco_nuts3`, `gisco_lau`, `statbel_income`, `cems_emsr517_germany_2021`, `cems_emsr518_belgium_2021`), so the honest claim is the narrower one. Claim the coverage you have: "every input is traceable to a URL and a stated purpose, and about three in four carry a verification date" survives a jury opening the file. "Licence for every input", and "a licence on every dataset we redistribute", do not. |
| Diversity and fairness | The equity lens: exposure broken down by age and income, not only a total. Plus: who is *missing* from the data (undocumented residents, people in temporary housing). |
| Environmental and societal well-being | The token budget you measured (`toon_io.token_report`), and the choice of a small model where a large one was not needed. |
| Accountability | Named owner per deliverable; the limits section states what the work cannot claim. |

## Data governance is also licence hygiene

The cheap version of this requirement is "we used open data". The version a JRC
jury can check is: which licence, and what it forbids.

- **The Walloon trap.** The *aléa d'inondation* records are CC-BY 4.0 and
  redistributable. The neighbouring "Zones inondables – période de retour"
  records are CPU Type A SPW: the data may **not** be passed to a third party,
  and printing is capped at 1:10,000. A published map built on them is fine; a
  public repository containing them is not. This repository goes public, so it
  uses the CC-BY records — and reproduces the SPW attribution string verbatim,
  because CC-BY is a condition, not a courtesy.
- **Credentialed sources are not open data.** The Risk Data Hub needs an EU Login
  token, so what the repo ships is the derived figure and the query, never a
  bulk copy of the Hub's rows. Its values are also averages across the sources
  each row names in `data_source_list` (DFO, EM-DAT, HANZE, and NOAA on a few),
  which makes attributing them correctly part of transparency rather than a
  footnote.
- **A missing number must stay missing.** `src/rdh.py` raises rather than
  returning an empty list when it has no token: "we did not look" and "we looked
  and found nothing" are different statements, and collapsing them is how an
  absence of data becomes a claim of absence in a brief.

## Tracing: let the tool keep the log

LangGraph traces every node automatically once `LANGSMITH_TRACING=true` and
`LANGSMITH_API_KEY` are set — no code to write. Each LLM call made through the
graph in `src/workflow.py` then has its prompt, its output, its latency and its
token count recorded and inspectable afterwards. **The live UIs do not run that
graph**: `POST /api/draft` and the Streamlit draft tab call the model directly,
so their calls are not in a LangGraph trace, and for them the hand-written log
below is the record. Their human gate is the separate approve action, which
re-runs the offline checks on the approved text and writes the verdict next to
it in `data/processed/approved.md`.

That is HLEG requirement 7 (accountability) as evidence rather than a claim,
produced as the work runs rather than reconstructed afterwards.
`src.workflow.tracing_status()` reports whether it is actually on, including the
half-configured case: tracing asked for with no key records nothing and warns
about nothing.

**State the cost in the AI sheet, not in a footnote.** Traces are sent to
LangChain's servers, so prompts and model outputs leave the machine. That is
acceptable here because the corpus is public EU documents and the exposure table
is open data. It would not be acceptable on anything you would not publish, and
saying so out loud is itself the responsible-AI point: you knew what left, and
why it was allowed to.

**During the event (29-30 October), no personal keys.** Annex 3 allows only
the account the organisers gave and the team's API key; a personal
`ANTHROPIC_API_KEY` or `GROQ_API_KEY` stays out of `.env`, and the kit's model
calls go through the team key or local Ollama. Tokens are limited for the two
days and Claude Code uses them fastest, so use it sparingly.

Keep the hand-written log as well. The trace records what the machine did; the
log records **what a human checked and what they rejected**, which is the part no
tool can produce.

## The AI usage log

Keep this as you go, in the team's AI log. It is not submitted itself: it is
the running note the **Annex 7 AI sheet** is compiled from, and Annex 3 asks for
that note "from the first hour". Writing it live costs nothing; reconstructing it
at the end is both painful and dishonest.

At the event, add the columns the Annex 7 sheet asks for, so compiling it is a
copy rather than a memory exercise: the **stage** (1 understanding the case and
data, 2 loading and preparing data, 3 analysis and code, 4 maps and charts,
5 desk research and sources, 6 interpreting results, 7 recommendation and
brief, 8 policy tool), the **AI level** in the sheet's own words (no AI / team
led, AI assisted or checked / AI and team together / AI did most of it / AI
misled us here), the **error and how it was noticed**, and a ★ on the prompts
that are candidates for the sheet's **three key prompts** (prompt text, tool,
why it worked). No names anywhere: the sheet takes the team number only.

| Time | Stage | Tool / model | Task (★ key prompt: quote it) | AI level | What a human checked | Error, and how noticed | Outcome |
|---|---|---|---|---|---|---|---|
| Thu 11:20 | 3 | [model] | Draft the zonal-stats function | AI and team together | Ran it against a hand-computed 3×3 raster | Off-by-one window, noticed on the 3×3 check | Accepted after 1 fix |
| Thu 15:40 | 5 | [model] | Summarise Art. 7 of the Floods Directive | Team led, AI assisted or checked | Read the article; the citation was correct | none | Accepted |
| Fri 10:05 | 7 | [model] | Propose recommendation wording | AI misled us here | Checked every figure against the frozen table | Invented a cost figure, noticed because no source held it | Rewritten by hand |

The rows already in the team's AI log predate the annexes and keep their
five columns, and the Streamlit log form (`app/streamlit_app.py`) still writes
those five; start the event's table under its own heading in the same file.

**Include at least one rejection.** A log with no rejection reads as a log nobody
actually kept. The rejection is the evidence of oversight.

## Say what AI must not decide

FARI's manifesto is explicitly anti-hype: it warns against investing in hyped
business models that cannot serve the common good. The strongest line in the
demo is a limit, not a capability.

In this work, AI should **not** decide:

- **Who gets protected first.** The ranking of communes is a political choice
  about which lives and livelihoods come first. The analysis informs it; it does
  not make it.
- **The vulnerability weights.** They encode a value judgement about whose
  exposure counts more. They must be explicit, documented, and tested for
  sensitivity.
- **The depth threshold** at which a cell counts as flooded. It changes the
  headline number and must be a stated, defended choice.
- **Anything a resident would experience directly** — an evacuation order, an
  alert — without a human in the loop.

## One caution on the AI Act

It is tempting to assert that a flood-risk tool is "high-risk under Annex III".
Check the actual text before claiming it: the annex is specific, and a jury that
includes JRC lawyers will know it better than you. Say what you verified and
nothing more. `docs/policy_context.md` carries the researched position.

A safer and still strong framing: the system is a **decision-support tool for a
public authority**, so regardless of its formal classification the team applied
the transparency and human-oversight expectations that the AI Act and the HLEG
guidelines set out.

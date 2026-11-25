# Responsible AI

The grid is the seven requirements of the EU High-Level Expert Group's Ethics Guidelines
for Trustworthy AI (the framework FARI's manifesto commits to). What the kit does under
each, and what it checks, is below; the pipeline is in [workflow.md](workflow.md).

| Requirement | What the kit does |
|---|---|
| Human agency and oversight | The AI proposes, a human decides: thresholds, weights and rankings are stated defaults, and nothing is written to the brief without the approve action. |
| Technical robustness and safety | Retrieval refuses rather than guesses when no source supports an answer, and a missing corpus is reported as unavailable (503), never as "the corpus is silent". Retrieved passages are fenced, and any `<source>` tag inside them is neutralised so a scraped page cannot forge one. Every draft is checked offline for citations out of range (grouped markers like `[S1, S9]` are checked one by one), numbers no passage or table holds, and claim sentences with no citation; the sentences answered "I DON'T KNOW" are shown as gaps. An approval citing a source outside the ones supplied is refused; one citing nothing is recorded with a warning. The checks cannot see a flipped negation or a claim cited to the wrong passage: say so. |
| Privacy and data governance | Aggregated open data only (population grids, not individuals); no personal data in any prompt; each input's licence recorded in `config/sources.yaml`. |
| Transparency | Public repository; `sources.yaml` gives a URL, a purpose and (for most entries) a verification date and licence for every input; the AI usage log records what a human checked. |
| Diversity, non-discrimination and fairness | Exposure broken down by age (share over 65) and poverty rate, not only a total; the people missing from the data are named in [limitations.md](limitations.md). |
| Environmental and societal well-being | Token use is measured (`toon_io.token_report`) and tables are sent in the compact TOON form. One model serves drafting, the question parser and translation alike; picking a smaller model per task is not built. |
| Accountability | A named owner per deliverable; the limits section states what the work cannot claim. |

## Licence hygiene

- The Walloon *aléa d'inondation* records are CC-BY 4.0 and redistributable; the
  neighbouring "Zones inondables - période de retour" records are CPU Type A SPW and may
  not be passed to a third party. The repository uses the CC-BY records and reproduces
  the SPW attribution verbatim.
- Credentialed sources are not open data: the Risk Data Hub needs an EU Login token, so
  the repository ships derived figures and the query, never a bulk copy. Its values
  average several sources (DFO, EM-DAT, HANZE), which must be attributed.
- A missing number stays missing: `src/rdh.py` raises when it has no token, because
  "we did not look" and "we looked and found nothing" are different statements.

## Tracing and the usage log

With `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`, every node of the graph in
`src/workflow.py` is traced (prompt, output, latency, tokens); `src.workflow.tracing_status()`
reports whether it is really on. The live UIs do not run that graph: `POST /api/draft` and
the Streamlit draft tab call the model directly, and their human gate is the approve
action, which re-runs the offline checks on the approved text and writes the verdict next
to it in `data/processed/approved.md`. Traces leave the machine for LangChain's servers,
which is acceptable only because the corpus and tables are public.

The trace records what the machine did; the usage log (`docs/ai_usage_log.md`, written
by the Streamlit "AI log" tab and kept out of git, see `src/usage_log.py`) records what a
human checked and rejected, which no tool produces. Keep a rejection in it:
a log without one reads as a log nobody kept.

## Say what AI must not decide

- **Who gets protected first.** The ranking of regions is a political choice.
- **The vulnerability weights.** They encode whose exposure counts more; they must be
  explicit and tested for sensitivity.
- **The depth threshold** at which a cell counts as flooded; it changes the headline.
- **Anything a resident would experience directly** (an evacuation order, an alert)
  without a human in the loop.

## The AI Act

Do not assert that a flood-risk tool is high-risk under Annex III without reading the
annex. The defensible framing is a decision-support tool for a public authority to which
the transparency and human-oversight expectations of the AI Act and the HLEG guidelines
were applied anyway ([policy_answer.md](policy_answer.md#5-the-responsible-ai-layer)).

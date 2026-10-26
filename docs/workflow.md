# Why a workflow and not an agent

Applying the BXL-Gebru-1 GenAI course (`04-Workflows`, `03-AI_agents`) to this
deliverable. This page is also your answer when the jury asks "what stopped the
model from writing the brief itself?".

## The distinction, and why it decides the design

An **agent** chooses its own next step. A **workflow** follows a path the author
fixed in advance.

For a document a public authority might act on, the path has to be inspectable
*before* it runs and explainable *after*. An agent that can decide to skip
verification because it judged the draft good enough is exactly the autonomy this
deliverable should not have.

So `src/workflow.py` is a fixed graph:

```
retrieve ──► draft ──► verify ──► approve ──► END
   │                                 ▲   (a weak draft arrives flagged)
   └──► refuse ──────────────────────┘   (nothing retrieved: the human still sees it)
```

One LLM call per run, at most. No tool loop, no redraft loop. The graph cannot take an action nobody
designed, and that sentence is worth more to a jury than any capability claim.

### Which path is live

The graph is **not** what the two UIs run. `POST /api/draft` (the React UI) and
the Streamlit draft tab each call `rag.complete` directly, then run the same
offline checks (`rag.verify`) on the answer and show them beside it. Their
approval gate is not LangGraph's `interrupt()` but a separate human action -
the "Approve for the brief" button, or `POST /api/approve` - which re-verifies the text it is
given and is the only thing that writes to `data/processed/approved.md`. So
the live path has the same shape (retrieve, one call, verify, a human approves)
without the graph, and the `RECURSION_LIMIT` / `MAX_REDRAFTS` / `MIN_GROUNDING`
guards below apply only when `src/workflow.py` is run - by its tests, or by the
snippet at the end of this page. Wiring the graph into the routes is a design
decision that has not been taken.

## Trigger → Process → Action

The course's mental model, mapped onto the brief pipeline:

| Stage | Here |
|---|---|
| **Trigger** | A frozen exposure table plus a question |
| **Process** | retrieve → draft → verify |
| **Action** | Write a brief section — **but only past a human approval gate** |

The action is the only step with a consequence outside the system, and it is the
one behind the gate. That is the whole design in one line.

## The four guards, and what each prevents

| Guard | Value | Prevents |
|---|---|---|
| `RECURSION_LIMIT` | 8 | A confused graph cycling until the API budget is gone |
| `MAX_REDRAFTS` | 0 | A second paid call: a weak draft is not re-rolled, it is flagged |
| `MIN_GROUNDING` | 0.7 | A draft whose vocabulary drifted away from the passages arriving unflagged. It is the share of the draft's content words found in any passage - not a share of cited sentences, and blind to numbers and negations |
| `interrupt()` | — | Anything at all reaching the brief without a human reading it (in the graph; the live routes use a separate approve call) |

The redraft limit is 0 on purpose: a redraft resent the same prompt, so it was a
re-roll rather than a correction, and it doubled the cost of the drafts that
needed the most scrutiny. A weak draft goes to the human with its grounding
score and its issues: invalid citations, unsupported numbers and uncited sentences. A person reading a draft marked "weakly
grounded" is a better outcome than a model asked to try again blind.

## Human-in-the-loop: which pattern, and why

The course lists four HITL patterns. This pipeline uses two, deliberately:

- **Approval gate** — the graph pauses at `approve` until a person resumes it.
  This is HLEG requirement 1 (human agency and oversight) made executable instead
  of asserted.
- **Confidence threshold** — below `MIN_GROUNDING`, the draft is flagged at the
  gate rather than passed silently. Automate when the result is strong;
  escalate to the human when it is not.

One detail worth defending out loud: when the human edits rather than approves,
the edit is used **as-is**. It is not fed back to the model to rewrite, because
that would hand the last word back to the machine.

## Idempotency, in `src/fetch.py`

The course's framing: "add £50" versus "make sure the balance is £50". Running
`fetch_all()` twice must not download twice.

So `_fetch_one` checks for a non-empty file on disk first and, if it passes the
same body check a fresh download must pass (`why_not_a_document_on_disk`),
returns its hash without touching the network; one that fails is moved aside as
`<name>.rejected` and fetched again. A hackathon connection drops often enough that you
*will* run collection several times, and a half-finished run should only cost you
the files that are actually missing.

**Idempotency is only as good as what counts as "already fetched".** Five entries
in `sources.yaml` used to point at the *directory* holding their files, and a
directory listing is valid HTML comfortably above the minimum document size — so
`_fetch_one` stored the listing as the data, and the disk check then declared the
source permanently done. A silent success, repeated on every later run, with no
data in it. `expand()` is the fix: an entry's `files:` list becomes one job per
file, ids become `<entry id>/<file stem>`, and the count `fetch_all` prints is
the number of jobs (56 for `geodata` and 84 across all three sections, with
`api` and `folder` entries skipped rather than counted; derived from
`sources.yaml` on 25 October 2026) rather than of
declared entries, of which there are 73. Entries with no `files:` key pass through untouched, so every
single-file source keeps its previous on-disk path.

## Verification is not an LLM call

`_verify`, like the two live draft routes, calls `rag.verify` offline, in
Python: citation markers in range, lexical grounding, every number in the draft
found in a passage or in the table (`unsupported_numbers`), and a citation on
every claim sentence (`uncited_sentences`). Asking a model to grade its own
output is not a check — it is a second opinion from the same source, and it
costs money and latency to be told what you want to hear.

These checks look at form, not meaning. They do not catch a negation flipped
("does not require"), a claim cited to the wrong passage, or a true figure
attached to the wrong region. The human reading the passages is the check for
those, which is why the gate shows the passages and not only the scores.

This is the same cite-or-refuse machinery as the `grounded-rag` project, which
means it is already tested and you can explain it from memory.

## What to say in the demo

> The pipeline is a fixed path, not an agent. It retrieves, drafts once,
> verifies, and then stops: nothing reaches the brief until one of us has read
> it and approved it, and the approval re-checks the text we approved.
> Verification is offline Python, not a second model grading the first - it
> checks citations and figures, and we read the passages for meaning. And the
> model never saw a number we had not already frozen.

## Running it

`langgraph` and `langchain-core` are already in `requirements.txt`.

```python
from langgraph.types import Command
from src.workflow import RECURSION_LIMIT, build_graph
from src.toon_io import to_toon

app = build_graph()               # keep it: its checkpointer holds the paused run
config = {"configurable": {"thread_id": "brief-1"}, "recursion_limit": RECURSION_LIMIT}
state = app.invoke({"question": "Which communes should be prioritised for a warning system?",
                    "exposure_toon": to_toon(frozen_exposure_table, "exposure")}, config)
print(state["__interrupt__"])     # the draft awaiting your decision
app.invoke(Command(resume="approve"), config)   # or resume with your edited text
```

`run()` is the one-shot form of the first two calls. It builds its own graph
and returns the paused state (the payload is under `__interrupt__`) without the
graph, so it cannot be resumed: use it to look at a
draft, and `build_graph()` to approve one.

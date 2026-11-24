# Why a workflow and not an agent

An agent chooses its next step; a workflow follows a path fixed in advance. For a
document a public authority might act on, the path must be inspectable before it runs and
explainable after, and an agent that can skip verification because it judged its draft
good enough has exactly the autonomy this tool should not have. So `src/workflow.py` is
a fixed graph:

```
retrieve --> draft --> verify --> approve --> END
   |                                 ^   (a weak draft arrives flagged)
   `--> refuse ----------------------'   (nothing retrieved: the human still sees it)
```

One model call per run at most; no tool loop, no redraft loop. The only step with a
consequence outside the system, writing a brief section, sits behind the approval gate.

## Which path is live

The graph is not what the two UIs run. `POST /api/draft` and the Streamlit draft tab call
`rag.complete` directly, run the same offline checks (`rag.verify`) and show them beside
the answer. Their gate is a separate human action ("Approve for the brief", or
`POST /api/approve`), which re-verifies the text it is given and is the only writer of
`data/processed/approved.md`. Blank text is refused, and the verdict stamped next to the
text says its numbers were checked against the sources the client sent, because the
server does not keep the draft's passages. The guards below apply when `src/workflow.py` runs (its
tests, or the snippet at the end). Wiring the graph into the routes is an open decision.

## The four guards, and what each prevents

| Guard | Value | Prevents |
|---|---|---|
| `RECURSION_LIMIT` | 8 | a confused graph cycling until the API budget is gone |
| `MAX_REDRAFTS` | 0 | a second paid call: a redraft resends the same prompt (a re-roll, not a correction), so a weak draft is flagged, not retried |
| `MIN_GROUNDING` | 0.7 | a draft whose vocabulary drifted from the passages arriving unflagged; it is the share of content words found in any passage, blind to numbers and negations |
| `interrupt()` | - | anything reaching the brief without a human reading it |

When the human edits rather than approves, the edit is used as-is; it is never sent back
to the model, which would hand the last word to the machine. A reply only counts as an
edit when it reads like brief text. One to three words ("Approve.", "yes", "Not
approved"), or a reply that opens with an approval or refusal word, is read as a
decision; a decision that is neither a plain `approve` nor `reject` is rejected with a
reason, so nothing is published by accident. To replace a short section, use the
`edit:` form. Approving a refused draft writes nothing: the refusal notice is not brief
text.

## Verification is not a model call

`rag.verify` runs offline in Python: citation markers in range, lexical grounding, every
number found in a passage or the table (`unsupported_numbers`), a citation on every claim
sentence (`uncited_sentences`). A model grading its own output is a second opinion from
the same source. These checks look at form, not meaning: they miss a flipped negation, a
claim cited to the wrong passage and a true figure on the wrong region, which is why the
gate shows the passages, not only the scores.

## Idempotency in `src/fetch.py`

`fetch_all()` run twice must not download twice. `_fetch_one` returns the hash of a
non-empty file that passes the same body check as a fresh download
(`why_not_a_document_on_disk`); one that fails is moved aside as `<name>.rejected` and
refetched. Entries must point at files, not directories: a directory listing is valid HTML
above the minimum size and would be stored as the data, a silent permanent success, so
`expand()` turns an entry's `files:` list into one job per file.

## Running it

```python
from langgraph.types import Command
from src.workflow import RECURSION_LIMIT, build_graph
from src.toon_io import to_toon

app = build_graph()               # keep it: its checkpointer holds the paused run
config = {"configurable": {"thread_id": "brief-1"}, "recursion_limit": RECURSION_LIMIT}
state = app.invoke({"question": "Which communes should be prioritised for a warning system?",
                    "exposure_toon": to_toon(frozen_exposure_table, "exposure")}, config)
print(state["__interrupt__"])     # the draft awaiting a decision
app.invoke(Command(resume="approve"), config)   # or resume with the edited text
```

`run()` is the one-shot form of the first call; it cannot be resumed.

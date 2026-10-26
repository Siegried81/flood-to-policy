"""The brief pipeline as a LangGraph workflow, with an approval gate.

**Workflow, not agent — on purpose.** The course distinction applies directly
here: an agent decides its own next step, a workflow follows a path the author
fixed. For a deliverable that a public authority might act on, the path must be
inspectable before it runs, and every run must be explainable afterwards. Letting
a model choose whether to skip verification is exactly the autonomy this
deliverable should not have. So: a fixed `retrieve -> draft -> verify -> approve`
graph, one LLM call per node, no tool loop. The only branches are author-written
and deterministic: refuse when retrieval came back empty, redraft when the
offline check scored the draft weak.

That is also the single clearest thing to say to the jury about responsible AI:
the pipeline cannot take an action nobody designed.

Trigger -> Process -> Action, as the course frames it:
  trigger = a frozen exposure table and a question
  process = retrieve, draft, verify
  action  = write the brief section, but only past a human approval gate

**Not the live path.** No route calls this graph: `POST /api/draft` and the
Streamlit draft tab call `rag.complete` directly, run the same offline checks
(`rag.verify`) on the result, and approval is a separate button or
`POST /api/approve`. This module is the same pipeline made explicit as a graph -
retrieve, draft, verify, and a LangGraph `interrupt` as the human gate - run by
its tests and by a caller that imports `run`. What the live routes have instead of
the `interrupt` is the separate approval call, which re-verifies the text it is
given.

Install: `pip install langgraph langchain-core`. The module imports lazily so the
rest of the kit works without them.
"""

from __future__ import annotations

import os
import re
from typing import Literal, TypedDict


def tracing_status() -> dict:
    """Whether LangSmith tracing is on, and what that means for the brief.

    LangGraph traces automatically once `LANGSMITH_TRACING=true` and
    `LANGSMITH_API_KEY` are set - no code required. This function exists to make
    the state *visible*, because the trace is the accountability evidence the
    responsible-AI deliverable asks for (HLEG requirement 7), and a deliverable
    that silently did not record anything is worse than one that says it did not.

    The cost, which belongs in the brief rather than in a footnote: traces are
    sent to LangChain's servers, so prompts and model outputs leave the machine.
    Acceptable here because the corpus is public EU documents and the exposure
    table is open data. It would not be acceptable on anything unpublishable.
    """
    enabled = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
    has_key = bool(os.getenv("LANGSMITH_API_KEY"))
    return {
        "enabled": enabled and has_key,
        "project": os.getenv("LANGSMITH_PROJECT", "flood-policy-kit"),
        # The half-configured case is the one worth naming: tracing asked for but
        # no key means nothing is recorded, and nothing warns you.
        "note": (
            "LANGSMITH_TRACING is true but no API key is set - nothing is being recorded."
            if enabled and not has_key
            else "Prompts and outputs are sent to LangChain's servers."
            if enabled and has_key
            else "Tracing off; the AI usage log in docs/ is then the only record."
        ),
    }

# A hard ceiling on graph steps. Without one a confused graph can cycle until the
# API budget is gone; the course calls this out and LangGraph builds it in.
# With no redraft the longest path is 4 supersteps - retrieve, draft, verify,
# approve - so 8 is a wide margin. The refusal path is retrieve, refuse,
# approve: 3.
RECURSION_LIMIT = 8
# How many drafts verification may ask for in all before a weak one goes to the
# human flagged (the counter is 1 after the first draft). 0 means exactly one
# model call per run: a weak draft is never sent back, because the redraft
# resent the same prompt - a re-roll, not a correction - and every run stays a
# single structured call. Raise it to 2 for one re-roll.
MAX_REDRAFTS = 0
# Below this `rag.grounding_score` - the share of the draft's content words found
# anywhere in the retrieved passages, NOT a share of cited sentences - the draft is
# flagged weak (and redrafted, if `MAX_REDRAFTS` allows). It is a confidence
# threshold in the course's sense: automate when high, escalate when low.
MIN_GROUNDING = 0.7


class BriefState(TypedDict, total=False):
    """Everything the graph carries. Explicit, because an opaque state is an
    unexplainable workflow - and explainability is the deliverable."""

    question: str
    exposure_toon: str  # the frozen table, encoded by src.toon_io
    passages: list[dict]
    # True when retrieval found nothing and no model was ever called. Read this
    # before `draft`: on a refusal `draft` holds the refusal statement, which is
    # written by this module and not by a model.
    refused: bool
    draft: str
    # Which provider answered the draft call, "anthropic", "groq" or "ollama", and why it
    # switched. Absent on a refusal, because nothing was generated.
    provider: str
    fallback_reason: str
    # Share of the draft's content words found in the retrieved passages. On the
    # refusal path it is 0.0 and measures nothing - `refused` is what separates
    # "we checked and it is ungrounded" from "there was nothing to check".
    grounding: float
    # An invalid citation as its number (`[S7]` is 7); every other finding as a
    # sentence naming it.
    issues: list[int | str]
    redrafts: int
    # The human's verdict: "approve", "edit" or "reject". `approved` is True only
    # for the first two; `final` is empty on a rejection, so a caller that writes
    # `final` into the brief without looking writes nothing rather than writing
    # the rejection itself.
    decision: str
    approved: bool
    final: str
    rejection_reason: str


def _retrieve(state: BriefState) -> BriefState:
    """Pull supporting passages from the policy corpus.

    Separate from drafting so the evidence exists before any prose does. If this
    returns nothing, the honest output is a refusal, not a confident paragraph.
    """
    from src.rag import search  # lazy: keeps the import cost off the other modules

    passages = search(state["question"], k=5)
    return {"passages": passages, "refused": not passages}


def _after_retrieve(state: BriefState) -> Literal["draft", "refuse"]:
    """Cite or refuse, made into an edge rather than a promise.

    `rag.search` returns [] when nothing clears the retrieval gate, and that empty
    list is the refusal - but a graph with no branch here drafted on it anyway:
    the model got a PASSAGES section containing one newline, scored 0.0 grounding
    with invented citations, was redrafted up to `MAX_REDRAFTS` times on the same
    zero evidence, and the flagged result still went to the human. Two paid calls
    to produce something nobody should read. Both UIs already refused at this
    point; this edge is the graph catching up with them.
    """
    return "refuse" if not state["passages"] else "draft"


def _refuse(state: BriefState) -> BriefState:
    """State the refusal, spend nothing, call no model.

    Deterministic text on purpose: there is no evidence to write from, so asking a
    model to phrase the refusal would be paying for the one sentence we can be
    certain of. `grounding` is set to 0.0 to keep the state shape stable for the
    gate, and it is not a measurement here - `refused` is the field that says so.
    """
    return {
        "refused": True,
        "draft": (
            "REFUSED: no passage in the policy corpus clears the retrieval gate for "
            f"this question, so no section was drafted.\n\nQUESTION: {state['question']}\n\n"
            "This text is written by the workflow, not by a model. Nothing here is a "
            "model answer, and nothing in the exposure table was interpreted."
        ),
        "grounding": 0.0,
        "issues": [
            "retrieval returned no passage; no draft was generated and no model was called"
        ],
        "redrafts": 0,
    }


def _draft(state: BriefState) -> BriefState:
    """One structured LLM call: the numbers and the passages in, a paragraph out.

    The prompt gets only the frozen exposure table and the retrieved passages, so
    the model has nothing else to draw a figure from. Anything it states that is
    not in those two inputs is a hallucination the verify step can catch.

    The passages go through `rag.fence`, like they do in both UIs. This path is the
    one that writes into the policy brief, so it is the last place that should be
    interpolating scraped corpus text straight into a prompt: a document that
    closes its own `</source>` and then issues instructions is the standard
    injection route for an open-web corpus, and `fence` is what neutralises it.
    `fence` numbers the blocks S1..Sn in the same order, so the citation markers
    the model writes still line up with `len(passages)` in `_verify`.
    """
    from src.rag import complete_with_provider, draft_prompt, fence

    prompt = draft_prompt(state["question"],
                          f"EXPOSURE TABLE:\n{state['exposure_toon']}",
                          fence(state["passages"]))
    answer = complete_with_provider(prompt)
    return {
        "draft": answer.text,
        "provider": answer.provider,
        "fallback_reason": answer.fallback_reason or "",
        "redrafts": state.get("redrafts", 0) + 1,
    }


def _verify(state: BriefState) -> BriefState:
    """Offline check: do the citations exist, is every claim cited, is every
    figure in a source, and is the draft grounded in them?

    Deliberately not an LLM call. A model asked to grade its own output is not a
    check, it is a second opinion from the same source - and it costs money and
    latency to be told what you want to hear.

    `issues` keeps an invalid citation as its bare number, as the gate has
    always shown it, and adds one string per unsupported number and per
    uncited sentence. The table counts as a source for numbers, since the
    prompt hands the model both.
    """
    from src.rag import verify

    check = verify(state["draft"], state["passages"], state.get("exposure_toon", ""))
    issues: list = list(check["invalid_citations"])
    issues += [f"number not in any passage or the table: {n}"
               for n in check["unsupported_numbers"]]
    issues += [f"sentence with no citation: {s}" for s in check["uncited_sentences"]]
    return {"grounding": check["grounding"], "issues": issues}


def _after_verify(state: BriefState) -> Literal["draft", "approve"]:
    """Redraft on a weak result while `MAX_REDRAFTS` allows it - by default never.

    The budget guard is the point: without it, a draft the model cannot ground
    loops forever. Past the limit the flagged draft goes to the human anyway,
    because a human reading a flagged draft is a better outcome than a workflow
    that never finishes.
    """
    weak = state["grounding"] < MIN_GROUNDING or state["issues"]
    return "draft" if weak and state.get("redrafts", 0) < MAX_REDRAFTS else "approve"


def _approve(state: BriefState) -> BriefState:
    """The approval gate. Nothing reaches the brief without a human saying so.

    This node is where LangGraph's `interrupt` pauses the graph until a person
    resumes it. It is HLEG requirement 1 (human agency and oversight) made
    executable rather than asserted, and it is what you point at when the jury
    asks what stopped the model from writing the brief by itself.
    """
    from langgraph.types import interrupt

    refused = bool(state.get("refused"))
    decision = interrupt(
        {
            "refused": refused,
            "draft": state["draft"],
            "provider": state.get("provider", "none - no model was called"),
            "fallback_reason": state.get("fallback_reason", ""),
            "grounding": state["grounding"],
            "issues": state["issues"],
            "ask": (
                (
                    "Retrieval found no supporting passage, so this is a refusal and not "
                    "a draft. "
                    if refused
                    else "Approve this text for the brief? "
                )
                + "Reply 'approve', or 'reject' (anything starting with no/reject/refuse "
                "is a rejection and records the rest as the reason), or give the edited "
                "text - prefix it 'edit: ' if it has to start with one of those words."
            ),
        }
    )
    return _record(decision, state["draft"])


# The closed set of words that open a refusal. A bare string starting with one of
# them is read as a rejection and never as replacement text. The set is closed
# and checked against the FIRST word only, so it is a vocabulary and not a
# sentiment guess - and `{"decision": "edit", ...}` or an "edit: " prefix forces
# an edit that legitimately starts with one of these words.
_REFUSAL_WORDS = frozenset("no nope reject rejected deny denied refuse refused veto".split())
_FIRST_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _record(decision: object, draft: str) -> BriefState:
    """Turn what the human sent into one of three recorded outcomes.

    Three, because `approved: True` on both of the old branches made a rejection
    unrepresentable: "No. This is wrong, do not publish it." came back as
    `approved: True` with that sentence as the brief text, a
    `{"decision": "reject"}` dict came back approved and stringified, and an
    accidental resume with `None` published the word "None".

    Free text is still an edit and is still used verbatim - never fed back to the
    model, because that would hand the last word back to the machine. What changed
    is that ambiguity now fails closed, and it fails closed asymmetrically on
    purpose: an edit misread as a rejection publishes nothing and says so, while a
    rejection misread as an edit puts the objection into a policy brief as if it
    were the section. The first is a visible annoyance, the second is the exact
    harm this kit is built against, so the tie goes to refusing.

    `approved` now means "a human chose text for the brief" and is False on a
    rejection, where `final` is "" rather than the reason: a caller that appends
    `final` without checking `approved` then appends nothing instead of appending
    the objection.
    """
    if isinstance(decision, dict):
        verdict = str(decision.get("decision", "")).strip().lower()
        why = str(decision.get("why") or decision.get("reason") or "").strip()
        if verdict == "approve":
            return {"decision": "approve", "approved": True, "final": draft}
        if verdict == "edit":
            text = decision.get("text") or decision.get("final") or ""
            if isinstance(text, str) and text.strip():
                return {"decision": "edit", "approved": True, "final": text}
            return _rejected("an 'edit' decision arrived with no replacement text")
        return _rejected(why or f"decision {verdict or 'missing'!r} is not approval")

    if isinstance(decision, str) and decision.strip():
        stripped = decision.strip()
        lowered = stripped.lower()
        if lowered == "approve":
            return {"decision": "approve", "approved": True, "final": draft}
        if lowered.startswith("edit:"):
            text = stripped[len("edit:"):].strip()
            if text:
                return {"decision": "edit", "approved": True, "final": text}
            return _rejected("an 'edit:' reply arrived with no replacement text")
        match = _FIRST_WORD.match(lowered)
        if match and match.group(0) in _REFUSAL_WORDS:
            return _rejected(stripped)
        return {"decision": "edit", "approved": True, "final": decision}

    return _rejected(f"resumed with no usable decision ({decision!r})")


def _rejected(reason: str) -> BriefState:
    """The one shape a rejection takes, so every caller reads it the same way."""
    return {"decision": "reject", "approved": False, "final": "", "rejection_reason": reason}


def build_graph(checkpointer=None):
    """Assemble the graph. A checkpointer is required for the approval gate.

    `interrupt` works by persisting the state and raising; without somewhere to
    persist to, the graph cannot be resumed and the gate silently does nothing.
    Passing an in-memory saver is fine for a two-day event.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(BriefState)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("refuse", _refuse)
    graph.add_node("draft", _draft)
    graph.add_node("verify", _verify)
    graph.add_node("approve", _approve)

    graph.add_edge(START, "retrieve")
    # The refusal still goes through the gate rather than straight to END: the
    # human is the one who should see that the corpus had nothing, and routing it
    # anywhere else would give the graph a second exit nobody inspects.
    graph.add_conditional_edges(
        "retrieve", _after_retrieve, {"draft": "draft", "refuse": "refuse"}
    )
    graph.add_edge("refuse", "approve")
    graph.add_edge("draft", "verify")
    graph.add_conditional_edges("verify", _after_verify, {"draft": "draft", "approve": "approve"})
    graph.add_edge("approve", END)

    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def run(question: str, exposure_toon: str, thread_id: str = "brief-1") -> dict:
    """Run until the approval gate, then return what the human must decide on.

    A refused question stops at the same gate with `refused: True` and a draft
    that states the refusal, so there is one place to look and one place to
    decide - but it gets there without a single model call.

    Returns the interrupt payload rather than a finished section: the caller - the
    Streamlit app, or you at 14:00 on Friday - shows it, takes a decision, and
    resumes the graph with `Command(resume=...)`.
    """
    app = build_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    return app.invoke({"question": question, "exposure_toon": exposure_toon}, config)

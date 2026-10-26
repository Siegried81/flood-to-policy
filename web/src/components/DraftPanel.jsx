import React, { useState } from "react";
import { approve, draft as requestDraft } from "../api.js";

/**
 * Drafting a brief section, behind an approval gate.
 *
 * The gate is the point of the component, not a feature of it. Nothing written
 * here reaches the brief until a person presses approve, and the verification
 * travels with the text so that press is informed rather than a rubber stamp.
 * This is also the clearest thing to show a jury asking what stopped the model
 * writing the brief by itself.
 */
export default function DraftPanel({ returnPeriod, approveTokenRequired = false }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [edited, setEdited] = useState("");
  const [state, setState] = useState("idle");
  const [error, setError] = useState(null);
  const [approved, setApproved] = useState(null);
  const [token, setToken] = useState("");

  const run = async () => {
    setState("working");
    setError(null);
    setApproved(null);
    try {
      const body = await requestDraft(question, returnPeriod);
      setResult(body);
      setEdited(body.draft ?? "");
    } catch (e) {
      setError(e.message);
    } finally {
      setState("idle");
    }
  };

  const send = async () => {
    try {
      // The edited text is sent exactly as the human left it. It is deliberately
      // never passed back through the model to polish, which would hand the last
      // word to the machine.
      const body = await approve(edited, token);
      setApproved(body.approved_at);
    } catch (e) {
      setError(e.message);
    }
  };

  const weak = result && (result.grounding < 0.7 || result.invalid_citations?.length);

  return (
    <section className="panel">
      <h2>Draft a brief section</h2>
      <p className="caption">
        The model sees only the frozen table and the retrieved passages, so any
        figure it states that is not in one of those is something verification can
        catch.
      </p>

      <div className="row">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && question && run()}
          placeholder="Which regions should be prioritised for a warning system, and why?"
          aria-label="The decision-maker's question"
        />
        <button onClick={run} disabled={!question || state === "working"}>
          {state === "working" ? "Drafting…" : "Draft"}
        </button>
      </div>

      {error && <p className="bad">{error}</p>}

      {result?.refused && (
        <div className="refusal" role="note">
          <strong>Refused — the corpus is silent on this.</strong>
          <p>
            No passage supports an answer, so nothing was generated. This is the
            designed behaviour, not a failure: rephrase using the documents’ own
            wording, or accept that the corpus does not cover it.
          </p>
        </div>
      )}

      {result && !result.refused && (
        <>
          <div className="verdict">
            <span className={result.grounding >= 0.7 ? "chip ok" : "chip warn"}>
              grounding {(result.grounding * 100).toFixed(0)}%
            </span>
            <span className={result.invalid_citations.length ? "chip bad" : "chip ok"}>
              {result.invalid_citations.length
                ? `invalid: ${result.invalid_citations.map((n) => `[S${n}]`).join(", ")}`
                : "all citations resolve"}
            </span>
            {/* Keyed on `available`, not on the object. When tiktoken cannot be
                loaded the server sends every count as null inside an object that
                is still truthy, so testing the object alone rendered "−null%
                tokens vs JSON" — a measurement the code never had. The
                unmeasured case says so and carries the server's reason; it must
                stay visually distinct from a measured 0%, which is the property
                this whole kit argues for. */}
            {result.tokens?.available ? (
              <span className="chip" title="Table encoded as TOON rather than JSON">
                −{result.tokens.saving_pct}% tokens vs JSON
              </span>
            ) : result.tokens ? (
              <span className="chip warn">token saving not measured</span>
            ) : null}
          </div>

          {result.tokens && !result.tokens.available && (
            <p className="caption warn-text">
              Token saving NOT measured here — {result.tokens.reason}. Run the
              count where tiktoken loads (WSL, or the container) before quoting a
              figure in the brief.
            </p>
          )}

          {result.prompt_rows != null && (
            <p className="caption">
              The model read {result.prompt_rows}{" "}
              {result.ranked ? "most exposed regions" : "regions, in file order,"}
              {result.return_period ? ` at the 1-in-${result.return_period} year flood` : ""}
              {result.ranked ? ", ranked by share" : ""} — an extract, so any
              European total in the draft is not from the table.
            </p>
          )}

          <p className="caption">
            Grounding counts shared words, not meaning: it catches an answer
            drifting away from its sources, not a subtle misreading that reuses
            their vocabulary. Read the passages before approving.
          </p>

          <details>
            <summary>{result.passages.length} passages retrieved</summary>
            {result.passages.map((p, i) => (
              <blockquote key={i}>
                <b>[S{i + 1}]</b> <code>{p.source}</code> · score {p.score}
                <p>{p.text}</p>
              </blockquote>
            ))}
          </details>

          <textarea
            value={edited}
            onChange={(e) => setEdited(e.target.value)}
            rows={12}
            aria-label="Draft, editable"
          />

          <div className="row">
            {/* Shown only when the server asks for it; held in this component's
                state for the session and never written anywhere. */}
            {approveTokenRequired && (
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Approve token"
                aria-label="Approve token"
                autoComplete="off"
              />
            )}
            <button
              className="primary"
              onClick={send}
              disabled={!edited.trim() || (approveTokenRequired && !token)}
            >
              Approve for the brief
            </button>
            {weak && (
              <span className="caption warn-text">
                Weakly grounded or carrying a bad citation — read it against the
                passages first.
              </span>
            )}
            {approved && <span className="chip ok">appended {approved}</span>}
          </div>
        </>
      )}
    </section>
  );
}

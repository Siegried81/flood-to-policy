import React, { useState } from "react";
import { search } from "../api.js";

/**
 * Search the policy corpus, with no model in the loop.
 *
 * It answers the question a reader should ask before drafting anything: what do
 * the documents actually say on this? It calls `/api/search`, the same retrieval
 * the Draft tab uses, so the passages shown here are the ones a draft would be
 * written from. No language model runs, which is why the tab stays on in the
 * hosted demo. A refusal (nothing clears the relevance gate) is shown as an
 * answer, and a missing corpus as the server's 503 message, never as an empty
 * list, because "the documents are silent" and "there are no documents here" are
 * different statements.
 */
export default function SearchPanel() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [state, setState] = useState("idle");
  const [error, setError] = useState(null);

  const run = async () => {
    setState("working");
    setError(null);
    setResult(null);
    try {
      setResult(await search(question, 5));
    } catch (e) {
      setError(e.message);
    } finally {
      setState("idle");
    }
  };

  return (
    <section className="panel">
      <h2>Search the sources</h2>
      <p className="caption">
        The passages the Draft tab would be written from, ranked by relevance. No
        model runs here: what you read is the documents' own text.
      </p>

      <div className="row">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && question.trim() && run()}
          placeholder="What does the Floods Directive require for shared river basins?"
          aria-label="Search the policy corpus"
          maxLength={2000}
        />
        <button onClick={run} disabled={!question.trim() || state === "working"}>
          {state === "working" ? "Searching…" : "Search"}
        </button>
      </div>

      {error && <p className="bad">{error}</p>}

      {result?.refused && (
        <div className="refusal" role="note">
          <strong>No passage clears the relevance bar.</strong>
          <p>
            The corpus was searched and holds nothing close enough to this question.
            Try the documents' own wording.
          </p>
        </div>
      )}

      {result && !result.refused && (
        <ol className="passages">
          {result.passages.map((p, i) => (
            <li key={i}>
              <blockquote>
                <b>[S{i + 1}]</b> <code>{p.source}</code> · score {p.score}
                <p>{p.text}</p>
              </blockquote>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

import React, { useEffect, useState } from "react";
import { getLanguages, translate as requestTranslation } from "../api.js";

/**
 * The approved brief, in the language the authority works in.
 *
 * Everything in this kit is written in English - the corpus, the code, this
 * interface and the draft next door. The authority that would act on the brief
 * is Belgian, and a recommendation is read in French, Dutch or German.
 *
 * So the translation sits BESIDE the English rather than replacing it. The
 * English stays the record, because it is the text whose figures were checked
 * against the frozen table; the translation is a rendering of it.
 *
 * The component's real job is the failure case. A translation may change every
 * word and may not change a single number, and a model will localise
 * `29,727,887` to `29 727 887` - correct - as readily as it will write
 * `29,7 millions`, round `16.9%` or move a `[S2]`. None of that looks wrong on
 * the page, so the server refuses such a translation with 422 and this panel
 * renders the refusal instead of the text. There is deliberately no way to
 * display a translation that failed the check.
 */
export default function TranslationPanel() {
  const [languages, setLanguages] = useState([]);
  const [language, setLanguage] = useState("fr");
  const [source, setSource] = useState("");
  const [result, setResult] = useState(null);
  const [state, setState] = useState("idle");
  const [error, setError] = useState(null);

  // Fetched rather than hardcoded: the list lives in `src/translate.py`, and a
  // copy here would drift the moment a language is added or removed.
  useEffect(() => {
    getLanguages()
      .then((body) => {
        setLanguages(body.languages ?? []);
        if (body.languages?.length) setLanguage(body.languages[0].code);
      })
      .catch((e) => setError(e.message));
  }, []);

  const run = async () => {
    setState("working");
    setError(null);
    setResult(null);
    try {
      setResult(await requestTranslation(source, language));
    } catch (e) {
      // Both the refusal (422) and an unreachable model (502) arrive here with
      // the server's own sentence. Shown as the error it is, never beside a
      // paragraph the reader could mistake for the translation.
      setError(e.message);
    } finally {
      setState("idle");
    }
  };

  return (
    <section className="panel">
      <h2>The brief in the language the authority works in</h2>
      <p className="note">
        The English section stays the record — it is the text whose figures were
        checked against the frozen table. A translation is a rendering of it, and
        one that moved a figure or a citation is refused rather than shown.
      </p>

      <label htmlFor="translate-source">English section</label>
      <textarea
        id="translate-source"
        rows={8}
        value={source}
        onChange={(e) => setSource(e.target.value)}
        placeholder="Paste the approved English section here."
      />

      <div className="row">
        <label htmlFor="translate-language">Into</label>
        <select
          id="translate-language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          {languages.map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={run}
          disabled={state === "working" || !source.trim()}
        >
          {state === "working" ? "Translating…" : "Translate"}
        </button>
      </div>

      {error && <p className="error">Not shown — {error}</p>}

      {result && (
        <>
          <p className="note">
            {result.numbers_checked} figures and {result.citations_checked}{" "}
            citations checked against the English, digit by digit.
          </p>
          <label htmlFor="translate-output">
            {result.language_name} — edit freely
          </label>
          <textarea
            id="translate-output"
            rows={8}
            value={result.text}
            onChange={(e) => setResult({ ...result, text: e.target.value })}
          />
          <p className="note">
            The check compares digits, not formatting: 29,727,887 and 29 727 887
            are the same number, and 29.7 million is not.
          </p>
        </>
      )}
    </section>
  );
}

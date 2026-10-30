import React, { useEffect, useState } from "react";
import { STATIC_BUILD, getConfig } from "./api.js";
import EuropeView from "./EuropeView.jsx";
import Event2021 from "./components/Event2021.jsx";

// Two views. "July 2021" opens first because it is the argument: the event, the
// people the 1-in-100-year map missed, and the date to act by. "Europe" holds
// the kit's exposure, vulnerability and drafting tabs as before.
//
// A static build has no API: both views read files shipped in dist/ (the July
// 2021 JSON, and the Europe view's frozen API answers), and the tabs that call
// a language model are switched off as in the hosted demo.
const VIEWS = ["July 2021", "Europe"];
const STATIC_CONFIG = { hosted: true, llm_enabled: false };

export default function App() {
  const [view, setView] = useState(VIEWS[0]);
  const [config, setConfig] = useState(null);

  useEffect(() => {
    if (STATIC_BUILD) return;
    // An API without /api/config predates hosted mode: treat it as local.
    getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  const hosted = STATIC_BUILD || Boolean(config?.hosted);

  return (
    <main className="shell">
      <header className="app-head">
        <div>
          <h1>Warn before the water, shelter where people have none</h1>
          <p className="caption">
            July 2021 floods in the Liege, Limburg and Aachen border area, in European context · Team 9
            {hosted && (
              <span className="chip demo-chip" title="Language-model and write features are off">
                {STATIC_BUILD ? "static demo" : "hosted demo"}
              </span>
            )}
          </p>
        </div>
        {VIEWS.length > 1 && (
          <nav className="views" role="tablist" aria-label="Views">
            {VIEWS.map((name) => (
              <button
                key={name}
                role="tab"
                aria-selected={view === name}
                className={view === name ? "view-btn on" : "view-btn"}
                onClick={() => setView(name)}
              >
                {name}
              </button>
            ))}
          </nav>
        )}
      </header>

      {view === "July 2021" && <Event2021 />}
      {view === "Europe" && <EuropeView config={STATIC_BUILD ? STATIC_CONFIG : config} />}
    </main>
  );
}

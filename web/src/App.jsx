import React, { useEffect, useState } from "react";
import { STATIC_BUILD, getConfig } from "./api.js";
import EuropeView from "./EuropeView.jsx";
import Event2021 from "./components/Event2021.jsx";
import TeamMap from "./components/TeamMap.jsx";

// Three views. "Team 9 map" opens first: it is the team's four-scene map, the
// one shown on the day, so a visitor lands on the shared work before the
// individual analysis. Opening on it means its 37 MB page loads with the app.
// "July 2021" is the argument: the event, the people the 1-in-100-year map
// missed, and the date to act by. "Europe" holds the kit's exposure,
// vulnerability and drafting tabs.
//
// A static build has no API: all views read files shipped in dist/ (the July
// 2021 JSON, the Europe view's frozen API answers, the team's HTML map), and the
// tabs that call a language model are switched off as in the hosted demo.
const VIEWS = ["Team 9 map", "July 2021", "Europe"];
const STATIC_CONFIG = { hosted: true, llm_enabled: false };
// When /api/config cannot be read the server's mode is unknown, so the model tabs
// are switched off: enabled tabs that answer 403 would read as a broken app.
const UNKNOWN_CONFIG = { hosted: false, llm_enabled: false, unknown: true };

export default function App() {
  const [view, setView] = useState(VIEWS[0]);
  const [config, setConfig] = useState(null);

  useEffect(() => {
    if (STATIC_BUILD) return;
    getConfig().then(setConfig).catch(() => setConfig(UNKNOWN_CONFIG));
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
            {config?.unknown && (
              <span className="chip" title="GET /api/config failed">
                API settings unreadable: model features are off
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

      {view === "Team 9 map" && <TeamMap />}
      {view === "July 2021" && <Event2021 />}
      {view === "Europe" && <EuropeView config={STATIC_BUILD ? STATIC_CONFIG : config} />}
    </main>
  );
}

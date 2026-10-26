import React, { useEffect, useMemo, useState } from "react";
import { getExposure, getGeometry, getMeta } from "./api.js";
import Choropleth from "./components/Choropleth.jsx";
import ContextPanel from "./components/ContextPanel.jsx";
import DraftPanel from "./components/DraftPanel.jsx";
import SortableTable from "./components/SortableTable.jsx";
import TranslationPanel from "./components/TranslationPanel.jsx";
import VulnerabilityPanel from "./components/VulnerabilityPanel.jsx";

// "Context" sits second, right after the exposure count it qualifies: the
// climate caveat is worth nothing if a reader meets it after writing the
// brief. It is offered whether or not the table was built - the panel renders
// the server's 404, which names the script, rather than the tab disappearing
// and the second table going unmentioned.
const TABS = ["Exposure", "Context", "Vulnerability", "Draft", "Translation"];

const finite = (value) => (Number.isFinite(value) ? value : null);

// The share is read off the row when the server sent one, and derived
// otherwise, so the column is present whichever metric the map is showing.
// Without a denominator it stays blank rather than showing a 0% that would read
// as "nobody".
const shareOf = (row) =>
  Number.isFinite(row.exposed_share)
    ? row.exposed_share
    : Number.isFinite(row.exposed_pop) && row.total_pop > 0
      ? row.exposed_pop / row.total_pop
      : null;

// Shares travel as fractions; the map shows them as percentages to one decimal,
// enough to separate the quantile breaks (1.0%, 2.3%, 3.9% ...) without false precision.
// A positive share below 0.05% would round to "0.0%" and read as nobody exposed.
const sharePercent = (v) => (v > 0 && v < 0.0005 ? "<0.1%" : `${(v * 100).toFixed(1)}%`);

export default function App() {
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("Exposure");
  const [returnPeriod, setReturnPeriod] = useState(null);
  const [exposure, setExposure] = useState(null);
  const [geometry, setGeometry] = useState(null);

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        setReturnPeriod(m.return_periods.at(-1) ?? null);
        // Geometry is optional: without it the ranking still works, so a missing
        // file degrades the map rather than breaking the page.
        if (m.has_geometry) getGeometry().then(setGeometry).catch(() => {});
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!meta) return;
    getExposure(returnPeriod).then(setExposure).catch((e) => setError(e.message));
  }, [meta, returnPeriod]);

  // Rank on share of residents, not absolute count: an absolute ranking just
  // ranks by population and tells a decision-maker nothing they did not know.
  const metric = exposure?.rows?.[0]?.exposed_share !== undefined
    ? "exposed_share"
    : "exposed_pop";

  const values = useMemo(() => {
    const map = new Map();
    for (const row of exposure?.rows ?? []) map.set(row[exposure.key], row[metric]);
    return map;
  }, [exposure, metric]);

  // Region names off the boundaries the map already loads, so every table can
  // print "Wittmund" beside "DE94H" without another request or another column
  // in the frozen tables. A code with no polygon falls back to itself.
  const names = useMemo(() => {
    const byCode = new Map();
    for (const feature of geometry?.features ?? []) {
      const code = feature.properties?.[meta?.key ?? "nuts_id"];
      if (code) byCode.set(code, feature.properties?.name ?? code);
    }
    return byCode;
  }, [geometry, meta]);

  const ranked = useMemo(
    () => [...(exposure?.rows ?? [])]
      .filter((r) => Number.isFinite(r[metric]))
      .sort((a, b) => b[metric] - a[metric])
      .slice(0, 15),
    [exposure, metric]
  );

  if (error) {
    return (
      <main className="shell">
        <h1>Flood exposure across European regions</h1>
        <div className="refusal"><strong>{error}</strong></div>
      </main>
    );
  }
  if (!meta) return <main className="shell"><p className="caption">Loading…</p></main>;

  return (
    <main className="shell">
      <header>
        <h1>Flood exposure across European regions</h1>
        <p className="caption">
          Frozen table · {meta.rows.toLocaleString()} rows · {meta.regions.toLocaleString()}{" "}
          regions · {meta.corpus_passages.toLocaleString()} corpus passages · computed{" "}
          {new Date(meta.frozen_at).toLocaleString()}. Every figure on this page and in
          every draft comes from this one run.
        </p>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? "tab active" : "tab"}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </nav>

      {tab === "Exposure" && exposure && (
        <section className="panel">
          <div className="row">
            <label>
              Return period
              <select
                value={returnPeriod ?? ""}
                onChange={(e) => setReturnPeriod(Number(e.target.value))}
              >
                {meta.return_periods.map((p) => (
                  <option key={p} value={p}>1-in-{p} years</option>
                ))}
              </select>
            </label>
            {/* The server sends null, not 0, when the table carries no
                exposed_pop column at all. "Not measured" and "zero" must not
                render the same, so neither is rounded into a number here. */}
            <span className="chip">
              {Number.isFinite(exposure.total_exposed)
                ? `${Math.round(exposure.total_exposed).toLocaleString()} exposed`
                : "exposure not measured"}
            </span>
            <span className="chip warn" title="Regions the hazard raster does not cover">
              {Number.isFinite(exposure.unmeasured)
                ? `${exposure.unmeasured} not measured`
                : "coverage unknown"}
            </span>
          </div>

          <p className="note">
            Return-period extents are <b>nested</b>: the 100-year zone contains the
            10-year one. Never add them together — compare them, or integrate over
            probability. Every figure on this tab is for the single period selected
            above, which is why there is no “all periods” option.
          </p>

          {/* The server picked the scenario because the request named none — only
              reachable if meta arrived with no return periods, but if it ever
              happens the reader is told rather than left to assume they chose. */}
          {exposure.defaulted_return_period && (
            <p className="note">
              No return period was requested, so the figures above are for the
              rarest one in the table (1-in-{exposure.return_period} years), not a
              summary of every scenario.
            </p>
          )}

          {/* Labelled from exposure.return_period, not from the selector: the
              selector can have moved since this response arrived, and a map
              captioned with a scenario it is not for is worse than no caption. */}
          <Choropleth
            geojson={geometry}
            values={values}
            idKey={exposure.key}
            // A share is a fraction on the wire; "≤4.2%" reads, "≤0.04" does not.
            format={metric === "exposed_share" ? sharePercent : undefined}
            label={
              metric === "exposed_share"
                ? `Share of residents exposed, 1-in-${exposure.return_period} year flood`
                : `Exposed population, 1-in-${exposure.return_period} year flood`
            }
          />

          <h3>Most exposed regions</h3>
          {/* Named, not coded. A table reading NL366 / ITC4C / TR611 is
              unreadable to anyone who does not work in NUTS, which is everyone a
              policy brief is addressed to. The code keeps a column of its own
              because it is what joins the row back to the boundaries and to
              Eurostat - traceability, not the label. Both fall back to the code
              so a table without the name columns still renders. */}
          <SortableTable
            rows={ranked}
            rowKey={(row) => row[exposure.key]}
            columns={[
              { label: "region", sort: (row) => row.region ?? row[exposure.key],
                render: (row) => row.region ?? row[exposure.key] },
              { label: "country", sort: (row) => row.country_name ?? row.country,
                render: (row) => row.country_name ?? row.country ?? "—" },
              { label: "residents", sort: (row) => finite(row.total_pop),
                render: (row) => (Number.isFinite(row.total_pop)
                  ? Math.round(row.total_pop).toLocaleString() : "—") },
              { label: "people exposed", sort: (row) => finite(row.exposed_pop),
                render: (row) => (Number.isFinite(row.exposed_pop)
                  ? Math.round(row.exposed_pop).toLocaleString() : "not measured") },
              { label: "share of residents", sort: shareOf,
                render: (row) => {
                  const share = shareOf(row);
                  return share === null ? "—" : (
                    <>
                      <span className="bar" style={{ width: `${share * 100}%` }} />
                      {(share * 100).toFixed(1)}%
                    </>
                  );
                } },
              // hazard_coverage travels next to exposed_pop as its qualifier: a
              // count over a partly observed region is a lower bound, and the
              // reader has to be able to see that without opening the parquet.
              { label: "coverage", sort: (row) => finite(row.hazard_coverage),
                render: (row) => (Number.isFinite(row.hazard_coverage)
                  ? `${(row.hazard_coverage * 100).toFixed(0)}%` : "unknown") },
              { label: exposure.key, sort: (row) => row[exposure.key],
                render: (row) => row[exposure.key], className: "code" },
            ]}
          />
        </section>
      )}

      {/* The return period is App state, shared with the map rather than owned by
          the panel: the ranking and the map must be answers about the same flood,
          and meta.indicators is the list the API itself offers, so the two UIs
          cannot weight different columns into the same index. */}
      {tab === "Vulnerability" && (
        <VulnerabilityPanel
          indicators={meta.indicators}
          regionKey={meta.key}
          returnPeriod={returnPeriod}
          returnPeriods={meta.return_periods}
          onReturnPeriod={setReturnPeriod}
          names={names}
        />
      )}

      {tab === "Context" && <ContextPanel names={names} />}

      {tab === "Draft" && (
        <DraftPanel
          returnPeriod={returnPeriod}
          approveTokenRequired={Boolean(meta?.approve_token_required)}
        />
      )}

      {tab === "Translation" && <TranslationPanel />}
    </main>
  );
}

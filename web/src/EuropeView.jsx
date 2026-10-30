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

// Tabs whose every action calls a language model or writes the brief. In the
// hosted demo the API refuses them with a 403, so they are greyed here and
// replaced by a notice instead of offering a button that can only fail.
const MODEL_TABS = new Set(["Draft", "Translation"]);

// The credits the data on this view requires, worded as in
// data/processed/DATA_NOTICE.md (tests/test_export_europe_web.py checks they
// still match it). One constant, rendered by the static and the API build
// alike: the licences bind wherever the figures are shown. The Copernicus
// Climate Change Service sentence and disclaimer are required verbatim.
export const EUROPE_SOURCES = [
  "Region codes, names and boundaries (NUTS 2024) — Source: Eurostat/GISCO. "
    + "© EuroGeographics for the administrative boundaries.",
  "Flood hazard — JRC / Copernicus Emergency Management Service, river flood hazard maps for "
    + "Europe v3.1.1, doi:10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81. © European Union, CC BY 4.0.",
  "Population and built-up surface — JRC Global Human Settlement Layer, GHS-POP and "
    + "GHS-BUILT-S R2023A, epoch 2025 at 1 km. © European Union, CC BY 4.0.",
  "Share over 65 and poverty rate — Source: Eurostat (demo_r_pjangrp3, ilc_li41). "
    + "Values were reshaped, and NUTS2 figures applied to their NUTS3 children. "
    + "Eurostat bears no responsibility for these derived figures.",
  "WFD river basin districts — © European Environment Agency, CC BY 4.0.",
  "Floods Directive areas of potential significant flood risk (APSFR) — Source: European "
    + "Environment Agency, reported by the Member States. The service publishes no licence; the "
    + "EEA default (CC BY 4.0) is assumed.",
  "Climate projections — Contains modified Copernicus Climate Change Service information 2026 "
    + "(doi:10.24381/cds.73237ad6), CC BY 4.0. Neither the European Commission nor ECMWF is "
    + "responsible for any use that may be made of the Copernicus information or data it contains.",
];

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
// enough to separate the quantile breaks (0.86%, 1.95%, 3.52% ... in the EU-27) without false precision.
// A positive share below 0.05% would round to "0.0%" and read as nobody exposed.
const sharePercent = (v) => (v > 0 && v < 0.0005 ? "<0.1%" : `${(v * 100).toFixed(1)}%`);

// The view opens on the 1-in-100 year flood, the scenario the brief, the pitch
// and the Directive's "medium probability" maps (Art. 6(3)(b)) all speak of, so
// the first figure a reader sees is the one they will hear. A table without
// RP100 falls back to its rarest period, as before.
export const DEFAULT_RETURN_PERIOD = 100;
export function defaultReturnPeriod(periods = []) {
  if (periods.includes(DEFAULT_RETURN_PERIOD)) return DEFAULT_RETURN_PERIOD;
  return periods.at(-1) ?? null;
}

// The European exposure views, as they were before the July 2021 view became
// the landing page. `config` comes from GET /api/config; null means "assume
// the local behaviour".
export default function EuropeView({ config }) {
  const modelsOff = config ? !config.llm_enabled : false;
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("Exposure");
  const [returnPeriod, setReturnPeriod] = useState(null);
  const [exposure, setExposure] = useState(null);
  const [geometry, setGeometry] = useState(null);
  // EU-27 first: the brief, the pitch and the Floods Directive speak of the
  // Member States. The other ten countries of the GISCO file stay one click away.
  const [scope, setScope] = useState("EU-27");

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        setReturnPeriod(defaultReturnPeriod(m.return_periods));
        // Geometry is optional: without it the ranking still works, so a missing
        // file degrades the map rather than breaking the page. `has_geometry`
        // says whether the server holds the polygons; a static build holds none
        // and fetches GISCO's own file in the browser instead (api.js).
        if (m.has_geometry || m.static) getGeometry().then(setGeometry).catch(() => {});
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

  // An API older than the eu27 flag sends rows without it: show them all
  // rather than none.
  const hasScope = exposure?.rows?.some((r) => typeof r.eu27 === "boolean") ?? false;
  const rows = useMemo(
    () => (exposure?.rows ?? []).filter((r) => scope !== "EU-27" || !hasScope || r.eu27),
    [exposure, scope, hasScope]
  );

  // Totals over the rows on screen, summed as the server sums them (unmeasured
  // regions skipped and counted apart), so the all-countries figure is the
  // server's own and the EU-27 one is its Member State part.
  const totals = useMemo(() => {
    const measured = rows.filter((r) => Number.isFinite(r.exposed_pop));
    return {
      exposed: exposure?.total_exposed == null
        ? null : measured.reduce((s, r) => s + r.exposed_pop, 0),
      unmeasured: exposure?.unmeasured == null ? null : rows.length - measured.length,
      countries: new Set(rows.map((r) => r.country)).size,
    };
  }, [rows, exposure]);

  const values = useMemo(() => {
    const map = new Map();
    for (const row of rows) map.set(row[exposure.key], row[metric]);
    return map;
  }, [rows, exposure, metric]);

  // The map draws the regions in scope only, so the other countries are left
  // out of the frame rather than greyed as "not measured", which they are not.
  const shown = useMemo(() => {
    if (!geometry || !exposure) return geometry;
    const ids = new Set(rows.map((r) => r[exposure.key]));
    return { ...geometry, features: geometry.features.filter((f) => ids.has(f.properties?.[exposure.key])) };
  }, [geometry, rows, exposure]);

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
    () => [...rows]
      .filter((r) => Number.isFinite(r[metric]))
      .sort((a, b) => b[metric] - a[metric])
      .slice(0, 15),
    [rows, metric]
  );

  if (error) {
    return (
      <div className="europe-view">
        <h2>Flood exposure across European regions</h2>
        <div className="refusal"><strong>{error}</strong></div>
      </div>
    );
  }
  if (!meta) return <div className="europe-view"><p className="caption">Loading…</p></div>;

  return (
    <div className="europe-view">
      <header>
        <h2 className="view-title">Flood exposure across European regions</h2>
        <p className="caption">
          Frozen table · {meta.rows.toLocaleString()} rows · {meta.regions.toLocaleString()}{" "}
          regions · {meta.corpus_passages.toLocaleString()} corpus passages. Every figure on this page and in
          every draft comes from this one run.
        </p>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((name) => {
          const off = modelsOff && MODEL_TABS.has(name);
          return (
            <button
              key={name}
              role="tab"
              aria-selected={tab === name}
              aria-disabled={off}
              title={off ? "Disabled in the hosted demo: it calls a language model" : undefined}
              className={`${tab === name ? "tab active" : "tab"}${off ? " tab-off" : ""}`}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          );
        })}
      </nav>

      {tab === "Exposure" && exposure && (
        <section className="panel">
          <div className="row">
            {/* A bar from the most to the least frequent flood, one notch per
                period in the table, so the nesting reads left to right. */}
            <label className="rp-bar">
              <span>
                Return period: <b>1-in-{returnPeriod} years</b>
              </span>
              <input
                type="range"
                aria-label="Return period"
                min={0}
                max={meta.return_periods.length - 1}
                step={1}
                value={Math.max(0, meta.return_periods.indexOf(returnPeriod))}
                onChange={(e) => setReturnPeriod(meta.return_periods[Number(e.target.value)])}
              />
              <span className="rp-ticks">
                {meta.return_periods.map((p) => (
                  <span key={p}>{p}</span>
                ))}
              </span>
            </label>
            {/* The server sends null, not 0, when the table carries no
                exposed_pop column at all. "Not measured" and "zero" must not
                render the same, so neither is rounded into a number here. */}
            {hasScope && (
              <label>
                Countries
                <select value={scope} onChange={(e) => setScope(e.target.value)}>
                  <option value="EU-27">EU-27</option>
                  <option value="All">All {new Set(exposure.rows.map((r) => r.country)).size} (EU-27, EFTA, candidates)</option>
                </select>
              </label>
            )}
            <span className="chip">
              {Number.isFinite(totals.exposed)
                ? `${Math.round(totals.exposed).toLocaleString()} exposed in ${totals.countries} countries`
                : "exposure not measured"}
            </span>
            <span className="chip warn" title="Regions the hazard raster does not cover">
              {Number.isFinite(totals.unmeasured)
                ? `${totals.unmeasured} not measured`
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
            geojson={shown}
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

      {modelsOff && MODEL_TABS.has(tab) && (
        <section className="panel">
          <div className="refusal">
            <strong>{tab} is disabled in the hosted demo.</strong> It calls a language
            model (and approving writes to the brief), which a public demo does not
            offer. Run the code locally to use it; every other tab works here.
          </div>
        </section>
      )}

      {!modelsOff && tab === "Draft" && (
        <DraftPanel
          returnPeriod={returnPeriod}
          approveTokenRequired={Boolean(meta?.approve_token_required)}
        />
      )}

      {!modelsOff && tab === "Translation" && <TranslationPanel />}

      {/* Under every tab, not only the map: the Context and Vulnerability
          tables show licensed figures too. */}
      <footer className="ev-footer">
        <p><b>Sources.</b> Figures derived from the datasets below and modified (aggregated per
          NUTS3 region, reprojected, thresholded); none of the publishers is responsible for them.</p>
        <ul>{EUROPE_SOURCES.map((s) => <li key={s}>{s}</li>)}</ul>
      </footer>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { getContext } from "../api.js";
import SortableTable from "./SortableTable.jsx";

/**
 * What qualifies an exposure figure, without being one.
 *
 * Three layers from a second frozen table: how river discharge moves under a
 * future climate, how much built-up surface sits in the flood zone, and how far
 * a region's basin reaches across a national border. None of them is an exposure
 * count, and none of them is ever merged into the exposure rows - the
 * vulnerability index is a weighted mean over whatever numeric columns it is
 * offered, so a climate percentage carried on an exposure row would be one
 * selection away from making "this region's rivers rise faster" a term in a
 * vulnerability score.
 *
 * The component's real job is the climate caveat. The number of model chains
 * per period is read off the table (`members` in the server's summary), and a
 * single chain cannot agree with itself: the server reports zero regions
 * agreeing on the sign for such a period. That zero is
 * indistinguishable from "the chains point different ways" unless the page says
 * which, and those are different claims - one is "we do not know yet", the other
 * is "we looked and the models conflict". So a one-chain period renders its
 * reason instead of a ranking, and there is deliberately no way to read a
 * direction off it.
 *
 * The median still shows, because it is a real measurement. It is simply not a
 * projection.
 */
/** A surface in square metres, rounded: see the call site for why. */
const squareMetres = (value) =>
  value == null ? "" : Math.round(value).toLocaleString();

/**
 * Country codes, or basin names, as a readable list.
 *
 * `shared_with` and `shared_basins` arrive as arrays, and JSX renders an array by concatenating
 * its items with nothing between them - so four countries printed as `DEFRLUNL`,
 * which is not a country and not four countries either.
 */
const countries = (value) => (Array.isArray(value) ? value.join(", ") : value);

export default function ContextPanel({ names = new Map() }) {
  const [body, setBody] = useState(null);
  const [period, setPeriod] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getContext()
      .then((payload) => {
        setBody(payload);
        // Opens on the LAST period: the far future is the one a reader is most
        // likely to quote, so it is the one that must arrive carrying its caveat.
        const periods = payload.climate_periods ?? [];
        if (periods.length) setPeriod(periods[periods.length - 1].period);
      })
      .catch((e) => setError(e.message));
  }, []);

  // The server's own sentence, which names the script that builds the table.
  // Rendered as the error it is rather than as an empty panel.
  if (error) return <p className="error">{error}</p>;
  if (!body) return <p>Loading the context table...</p>;

  const periods = body.climate_periods ?? [];
  const summary = periods.find((entry) => entry.period === period) ?? null;
  const suffix = period ? period.replace("-", "_") : null;
  const medianColumn = `change_pct_ensemble_median_${suffix}`;
  const rows = body.rows ?? [];
  // The direction test, mirroring `api.main.sign_column`: the robust column
  // (at least 80 % of the members, the IPCC AR6 convention) where the table
  // carries it, the unanimous one otherwise. With sixteen members unanimity is
  // a far stricter test than with two, so the robust rule is the one quoted;
  // the fallback keeps a table built before that column existed readable, and
  // the wording says which rule is being read.
  const robustColumn = `ensemble_robust_on_sign_${suffix}`;
  const hasRobust = rows.length > 0 && robustColumn in rows[0];
  const agreesColumn = hasRobust ? robustColumn : `ensemble_agrees_on_sign_${suffix}`;
  const agreesWording = hasRobust
    ? "at least 80 % of the members agree"
    : "every chain agrees";
  const agreeingCount = summary
    ? hasRobust
      ? summary.regions_robust_on_sign ?? 0
      : summary.regions_agreeing_on_sign
    : 0;
  // Set by the API: the chains agree on the direction but lie more than
  // MODEL_SPREAD_PP points apart, so the median is not a size to rank by.
  const uncertainColumn = `ensemble_size_uncertain_${suffix}`;
  // The name and the code head every table: the name to read, the code to
  // join the row back to Eurostat. A code with no polygon names itself.
  const regionColumns = [
    { label: "region", sort: (row) => names.get(row[body.key]) ?? row[body.key],
      render: (row) => names.get(row[body.key]) ?? row[body.key] },
    { label: body.key, sort: (row) => row[body.key],
      render: (row) => row[body.key], className: "code" },
  ];

  const agreeing = rows
    .filter(
      (row) =>
        row[agreesColumn] === true &&
        row[uncertainColumn] !== true &&
        row[medianColumn] != null
    )
    .sort((a, b) => b[medianColumn] - a[medianColumn])
    .slice(0, 15);

  const builtRp = body.built_up_return_period;
  const builtColumn = `built_share_exposed_rp${builtRp}`;
  const built =
    builtRp == null
      ? []
      : rows
          .filter((row) => row[builtColumn] != null)
          .sort((a, b) => b[builtColumn] - a[builtColumn])
          .slice(0, 15);

  // Rows where the country was covered at all: `apsfr_share` is null where the
  // dataset never carried that State's reporting, which is not the same as a
  // zero and must never be ranked as one.
  const declaredRows = rows.filter((row) => row.apsfr_share != null);
  const uncovered = rows.filter(
    (row) => row.apsfr_country_reported === false
  );
  const undeclared = declaredRows.filter((row) => !row.apsfr_declared);

  const shared = rows
    .filter((row) => row.shared_basin_share != null)
    .sort((a, b) => b.shared_basin_share - a.shared_basin_share)
    .slice(0, 15);

  return (
    <section>
      <h2>What qualifies the exposure figure</h2>
      <p>
        A second frozen table, built by <code>scripts/build_context.py</code>.
        Everything here describes the ground and the future around an exposure
        count without being one, which is why it is not merged into the exposure
        table.
      </p>

      <h3>River discharge, against the 1971-2000 reference</h3>
      <p className="caveat">
        The only forward-looking layer in the kit, and it is{" "}
        <strong>discharge, not depth</strong>: a future flow in cubic metres per
        second cannot be layered onto the inundation maps the exposure figures
        come from. What is defensible is the direction and the size of the
        change, read beside the exposure measured today, never a future headcount
        quoted as if it had been measured.
      </p>

      {periods.length === 0 && (
        <p>
          The context table carries no climate columns: the build found no CDS
          NetCDF for any period.
        </p>
      )}

      {periods.length > 0 && (
        <label>
          Period{" "}
          <select
            value={period ?? ""}
            onChange={(event) => setPeriod(event.target.value)}
          >
            {periods.map((entry) => (
              <option key={entry.period} value={entry.period}>
                {entry.period}
              </option>
            ))}
          </select>
        </label>
      )}

      {summary && (
        <dl className="metrics">
          <div>
            <dt>Median change</dt>
            {/* The median OF the per-region ensemble medians: a direction and a
                size, never a projected discharge. */}
            <dd>
              {summary.median_change_pct == null
                ? "not measured"
                : `${summary.median_change_pct > 0 ? "+" : ""}${summary.median_change_pct.toFixed(1)}%`}
            </dd>
          </div>
          <div>
            <dt>Model chains</dt>
            <dd>{summary.members}</dd>
          </div>
          <div>
            <dt>Regions measured</dt>
            <dd>{summary.regions_measured.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Agreeing on sign</dt>
            <dd>
              {agreeingCount.toLocaleString()}
              {/* The unanimous count travels beside the robust one, as in the
                  API, so neither rule is hidden behind the other. */}
              {hasRobust && (
                <> (unanimous: {summary.regions_agreeing_on_sign.toLocaleString()})</>
              )}
            </dd>
          </div>
        </dl>
      )}

      {summary && summary.single_member && (
        // The caveat that cannot be dropped, and the reason no ranking follows
        // it. Naming the missing member matters because "add a second chain" is
        // the action a reader can actually take.
        <p className="error">
          <strong>
            {summary.period} has one model chain, so no region agrees with
            anything.
          </strong>{" "}
          One member is one plausible world, not a projection: the median above
          is a real measurement and still licenses no sentence about the
          direction of the change. Add a second hydrological model for this
          period, the CDS archive offers <code>VIC-WUR-EUR-11</code> beside{" "}
          <code>E-HYPEgrid-EUR-11</code>, and the agreement count becomes
          readable.
        </p>
      )}

      {summary && !summary.single_member && (
        <>
          <p>
            The largest increases among the{" "}
            <strong>{agreeingCount.toLocaleString()}</strong>{" "}
            regions where {agreesWording} on the direction. The regions left
            out are not regions with no change: they are regions where the chains
            point different ways, which is a finding of its own.
          </p>
          {summary.regions_size_uncertain > 0 && (
            <p>
              Not ranked:{" "}
              <strong>{summary.regions_size_uncertain.toLocaleString()}</strong>{" "}
              regions whose members lie more than {summary.model_spread_pp} points
              apart (interquartile range beyond two members). They agree on the
              direction, not on the size, so their median is not a size to quote.
            </p>
          )}
          <SortableTable
            rows={agreeing}
            rowKey={(row) => row[body.key]}
            columns={[
              ...regionColumns,
              { label: "Median", sort: (row) => row[medianColumn],
                render: (row) => `${row[medianColumn]?.toFixed(1)}%` },
              { label: "Min", sort: (row) => row[`change_pct_ensemble_min_${suffix}`],
                render: (row) => `${row[`change_pct_ensemble_min_${suffix}`]?.toFixed(1)}%` },
              { label: "Max", sort: (row) => row[`change_pct_ensemble_max_${suffix}`],
                render: (row) => `${row[`change_pct_ensemble_max_${suffix}`]?.toFixed(1)}%` },
            ]}
          />
        </>
      )}

      {builtRp != null && (
        <>
          <h3>Exposed built-up surface, 1-in-{builtRp} year flood</h3>
          {/* The return period is in the column name for a reason: read against
              a different scenario's headcount it is two floods in one sentence. */}
          <p>
            Measured at RP{builtRp} only, which is why the period travels with
            the figure.
          </p>
          {/* Rounded at display, not in the table: the figure is a sum of
              sub-cell fractions, so its decimals are real arithmetic and
              meaningless as a surface. */}
          <SortableTable
            rows={built}
            rowKey={(row) => row[body.key]}
            columns={[
              ...regionColumns,
              { label: "Exposed, square metres", sort: (row) => row[`exposed_built_m2_rp${builtRp}`],
                render: (row) => squareMetres(row[`exposed_built_m2_rp${builtRp}`]) },
              { label: "Total, square metres", sort: (row) => row.built_total_m2,
                render: (row) => squareMetres(row.built_total_m2) },
              { label: "Share", sort: (row) => row[builtColumn],
                render: (row) => `${(row[builtColumn] * 100).toFixed(1)}%` },
            ]}
          />
        </>
      )}

      {declaredRows.length > 0 && (
        <>
          <h3>Declared at risk by the Member State</h3>
          <p>
            Areas of Potential Significant Flood Risk, designated under Article 5
            of the Floods Directive. Every other layer here measures what the
            water does; this one measures what a government said about it.
          </p>
          {uncovered.length > 0 && (
            // The caveat that stops a false accusation: the layer carries 26
            // country codes across both reporting cycles, and Ireland is not one
            // of them.
            <p className="error">
              <strong>
                {uncovered.length.toLocaleString()} regions sit in a country this
                dataset never covered.
              </strong>{" "}
              Their blank is not a finding about that country, and their share is
              left empty rather than set to zero.
            </p>
          )}
          <p>
            <strong>{undeclared.length.toLocaleString()}</strong> of{" "}
            {declaredRows.length.toLocaleString()} covered regions intersect no
            declared area. That is a question, not a verdict: a State may have
            assessed the area and concluded the risk is not significant, which the
            Directive allows.
          </p>
          {/* The UNDECLARED regions, not the most-declared ones. Sorting by
              share descending fills the table with regions a State covered
              entirely, which is the opposite of what this section is for: the
              question is where the modelled risk sits outside the designation. */}
          <SortableTable
            rows={undeclared.slice(0, 15)}
            rowKey={(row) => row[body.key]}
            columns={[
              ...regionColumns,
              { label: "Declared share", sort: (row) => row.apsfr_share,
                render: (row) => `${(row.apsfr_share * 100).toFixed(1)}%` },
              { label: "Cycle", sort: (row) => row.apsfr_cycle,
                render: (row) => row.apsfr_cycle },
            ]}
          />
        </>
      )}

      {shared.length > 0 && (
        <>
          <h3>Shared river basins</h3>
          <p>
            The share of a region&apos;s area sitting in a basin that crosses a
            national border, off the 2016 River Basin Management Plans, which is
            a reporting vintage like NUTS. Where this is high, a measure taken
            alone upstream is a measure taken on someone else&apos;s territory.
          </p>
          <SortableTable
            rows={shared}
            rowKey={(row) => row[body.key]}
            columns={[
              ...regionColumns,
              { label: "Shared share", sort: (row) => row.shared_basin_share,
                render: (row) => `${(row.shared_basin_share * 100).toFixed(0)}%` },
              { label: "Countries", sort: (row) => row.basin_countries_max,
                render: (row) => row.basin_countries_max },
              { label: "Basin", sort: (row) => countries(row.shared_basins),
                render: (row) => countries(row.shared_basins) },
              { label: "Shared with", sort: (row) => countries(row.shared_with),
                render: (row) => countries(row.shared_with) },
            ]}
          />
        </>
      )}
    </section>
  );
}

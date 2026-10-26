import React, { useEffect, useMemo, useState } from "react";
import { getEvent2021 } from "../api.js";

// The July 2021 story: four numbers that say why act, a story map per flooded
// place, the same comparison per country, then the limits. It renders
// `event_2021_web.json` (scripts/export_event_web.py) and computes nothing:
// every figure arrives already formatted by src/policy_tool.py, the same code
// that writes the single-file tool, so the two can never disagree on a number.
//
// The map is a classified PNG (20 m scoring grid, reduced) under an SVG overlay
// in the PNG's own pixel units; blue is water inside the 1-in-100-year zone,
// orange water outside it. The two differ in lightness as well as hue, so they
// read in greyscale and for colour-blind viewers.

const STEPS = {
  missed: "The map missed people",
  harm: "The harm",
  europe: "Not a one-off",
  when: "The window to act",
};

// "51 %" must never wrap between the number and its sign.
const nb = (text) => String(text ?? "").replace(/ %/g, " %");

// GeoJSON (Multi)Polygon in pixel units to SVG path data.
function geoPath(geometry) {
  if (!geometry) return "";
  const polys = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polys
    .flatMap((rings) => rings.map((ring) => `M${ring.map((p) => `${p[0]} ${p[1]}`).join("L")}Z`))
    .join("");
}

// Policy text carries a few <b> tags of our own (src/policy_tool.py constants);
// nothing else is allowed through.
function boldOnly(text) {
  const parts = String(text).split(/(<b>.*?<\/b>)/g);
  return parts.map((part, i) =>
    part.startsWith("<b>") ? <b key={i}>{part.slice(3, -4)}</b> : <React.Fragment key={i}>{part}</React.Fragment>
  );
}

function Hero({ hero }) {
  return (
    <section className="ev-hero" aria-label="Why act">
      {hero.map((h, i) => (
        <div key={h.id} className={`ev-arg ev-arg-${h.id}`}>
          <div className="ev-step">{i + 1}. {STEPS[h.id] ?? ""}</div>
          <div className="ev-big" data-hero={h.id} data-value={h.raw ?? ""}>{h.big}</div>
          <p className="ev-line">{nb(h.line)}</p>
          <p className="ev-small">{h.small}</p>
        </div>
      ))}
    </section>
  );
}

function Strip({ strip }) {
  return (
    <div className="ev-strip">
      {strip.map((s) => (
        <div key={s.country} className="ev-strip-cell" data-strip={s.country}>
          <span className="ev-strip-name">{s.name}</span>
          <span><b>{s.residents_shown}</b> residents reached</span>
          <span><b>{nb(s.share_shown)}</b> outside the 1-in-100-year zone</span>
        </div>
      ))}
    </div>
  );
}

function StoryMap({ place, showWater }) {
  const m = place.map;
  if (!m) {
    return <div className="ev-nomap">No map image for this place; its figures are on the right.</div>;
  }
  const { width: w, height: h } = m;
  const unit = Math.max(w, h);
  const fs = unit / 40;
  return (
    <div className="ev-stage" style={{ aspectRatio: `${w} / ${h}`, maxWidth: `calc(70vh * ${(w / h).toFixed(3)})` }}>
      <img
        src={m.png}
        width={w}
        height={h}
        alt={`Water seen in ${place.label}, inside and outside the 1-in-100-year zone`}
      />
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
        {m.nuts_d && <path className="ev-nuts" d={m.nuts_d} />}
        {showWater && m.observed && <path className="ev-water" d={geoPath(m.observed)} />}
        <path className="ev-outline" d={m.outline_d} />
        {m.towns.map((t) => {
          // Labels in the right half run leftward, so none is cut by the frame.
          const right = t.x > 0.55 * w;
          return (
            <g key={t.label} className="ev-town">
              <circle cx={t.x} cy={t.y} r={unit / 200} />
              <text
                x={right ? t.x - unit / 110 : t.x + unit / 110}
                y={t.y - unit / 150}
                textAnchor={right ? "end" : "start"}
                fontSize={fs}
              >
                {t.label}
              </text>
            </g>
          );
        })}
        {m.scale?.km && (
          <g className="ev-scale">
            <rect x={w * 0.03} y={h - fs * 1.6} width={m.scale.px} height={fs / 3} />
            <text x={w * 0.03} y={h - fs * 2} fontSize={fs}>{m.scale.km} km</text>
          </g>
        )}
      </svg>
    </div>
  );
}

function Facts({ place }) {
  const f = place.figures;
  const kind = place.graded
    ? "grading map: analysts drew the water through the streets"
    : "delineation map from radar: stops at walls, so a floor";
  return (
    <div className="ev-facts">
      <h3>{place.label}</h3>
      <div className="ev-fig">
        <div className="ev-n">{f.residents}</div>
        residents reached by the water ({f.km2} km² seen)
      </div>
      <div className="ev-fig">
        <div className="ev-n ev-out">{nb(f.share)}</div>
        of them lived outside the 1-in-100-year zone ({f.share_words})
      </div>
      <div className="ev-fig">
        <div className="ev-n">{f.residential}</div>
        homes in the water ({f.buildings} buildings in all)
      </div>
      <div className="ev-fig">
        <div className="ev-n">{place.graded ? f.destroyed : "n/a"}</div>
        {place.graded
          ? `buildings graded destroyed, ${f.damaged} damaged`
          : "destroyed buildings: not graded on this kind of map"}
      </div>
      <p className="ev-small">
        {place.country} · {place.key} · first satellite map; {kind}.
      </p>
      {place.later && (
        <p className="ev-small">
          A later satellite map of this area saw {place.later.km2} km² of water,{" "}
          {place.later.residents} residents, {nb(place.later.share)} of them outside the zone.
        </p>
      )}
    </div>
  );
}

function Locator({ locator, current, selectable, onPick }) {
  if (!locator) return null;
  return (
    <figure className="ev-locator">
      <svg viewBox={`0 0 ${locator.width} ${locator.height}`} role="img" aria-label="Where the chosen place is">
        <rect width="100%" height="100%" className="ev-loc-bg" />
        {locator.nuts_d && <path className="ev-loc-nuts" d={locator.nuts_d} />}
        <path className="ev-loc-borders" d={locator.borders_d} />
        {Object.entries(locator.aoi).map(([key, d]) => {
          const pick = selectable.has(key);
          return (
            <path
              key={key}
              d={d}
              className={`ev-loc-aoi${pick ? " pick" : ""}${key === current ? " on" : ""}`}
              onClick={pick ? () => onPick(key) : undefined}
            >
              <title>{key}</title>
            </path>
          );
        })}
        {locator.labels.map((l) => (
          <text key={l.text} x={l.x} y={l.y} className="ev-loc-label">{l.text}</text>
        ))}
      </svg>
      <figcaption className="ev-small">
        Every area Copernicus mapped in BE, DE and NL; the chosen one in orange.
      </figcaption>
    </figure>
  );
}

function Chart({ chart }) {
  const [rp, setRp] = useState(chart.default);
  return (
    <div className="ev-chart">
      <div className="ev-toggle" role="group" aria-label="Which flood map">
        {chart.return_periods.map((p) => (
          <button key={p} type="button" className={p === rp ? "on" : ""} aria-pressed={p === rp} onClick={() => setRp(p)}>
            1-in-{p}-year map
          </button>
        ))}
      </div>
      {chart.rows.map((r) => {
        const v = r.shares[String(rp)];
        const width = v == null ? 0 : Math.max(0, Math.min(v, 1)) * 100;
        return (
          <div key={r.country} className="ev-crow" title={`${r.name}, 1-in-${rp}-year map: ${r.shown[String(rp)]} outside`}>
            <div className="ev-cname">{r.name}</div>
            <div className="ev-track">
              <span className="ev-fill" style={{ width: `${width}%` }} data-value={v ?? ""} />
              <span className="ev-v">{nb(r.shown[String(rp)])}</span>
            </div>
          </div>
        );
      })}
      <div className="ev-axis" aria-hidden="true"><span>0 %</span><span>50 %</span><span>100 % of residents reached</span></div>
    </div>
  );
}

export default function Event2021() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [key, setKey] = useState(null);
  const [showWater, setShowWater] = useState(false);

  useEffect(() => {
    getEvent2021()
      .then((d) => {
        setData(d);
        setKey(d.places?.[0]?.key ?? null);
      })
      .catch((e) => setError(e.message));
  }, []);

  const selectable = useMemo(() => new Set((data?.places ?? []).map((p) => p.key)), [data]);

  if (error) return <div className="refusal"><strong>{error}</strong></div>;
  if (!data) return <p className="caption">Loading the July 2021 story…</p>;

  const place = data.places.find((p) => p.key === key) ?? data.places[0];
  const named = data.places.filter((p) => p.named);
  const more = data.places.filter((p) => !p.named);

  return (
    <div className="ev">
      <Hero hero={data.hero} />
      <Strip strip={data.strip} />
      <details className="ev-details">
        <summary>How we counted</summary>
        <ul>{data.how_we_counted.map((t, i) => <li key={i}>{boldOnly(t)}</li>)}</ul>
      </details>

      <h2 className="ev-h2"><span className="ev-kicker">The story map</span>Where the water went, and where the map expected it</h2>
      <div className="ev-places" role="group" aria-label="Choose a place">
        {named.map((p) => (
          <button key={p.key} type="button" className={p.key === place?.key ? "on" : ""} aria-pressed={p.key === place?.key} onClick={() => setKey(p.key)}>
            {p.label}
          </button>
        ))}
      </div>
      {more.length > 0 && (
        <div className="ev-places more" role="group" aria-label="Other mapped places">
          <span className="ev-small">Other mapped places:</span>
          {more.map((p) => (
            <button key={p.key} type="button" className={p.key === place?.key ? "on" : ""} aria-pressed={p.key === place?.key} onClick={() => setKey(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
      )}

      {place && (
        <div className="ev-story">
          <div className="ev-mapcol">
            <StoryMap place={place} showWater={showWater} />
            <ul className="ev-legend">
              {data.raster_classes.map((c) => (
                <li key={c.colour}><span className="ev-sw" style={{ background: c.colour }} />{c.label}</li>
              ))}
              <li><span className="ev-sw ev-sw-dash" />area Copernicus mapped (beyond it: unknown)</li>
            </ul>
            <label className="ev-check">
              <input type="checkbox" checked={showWater} onChange={(e) => setShowWater(e.target.checked)} />
              Outline the mapped water polygons
            </label>
            <p className="ev-small">
              The colours show where the water was; the percentage counts people, and people live
              unevenly along a valley, so the two need not match. Each pixel is about{" "}
              {place.map ? Math.round(place.map.pixel_m) : "n/a"} m across; a pixel with any water seen is
              drawn as water, and orange only when more of its water lies outside the zone than inside.
            </p>
          </div>
          <div className="ev-side">
            <Facts place={place} />
            <Locator locator={data.locator} current={place.key} selectable={selectable} onPick={setKey} />
          </div>
        </div>
      )}

      <h2 className="ev-h2"><span className="ev-kicker">Three countries</span>{data.chart.heading}</h2>
      <Chart chart={data.chart} />
      <p className="ev-small">
        Share of the residents the water reached (first satellite maps) who lived outside the JRC
        flood map. The bigger the flood a map assumes, the more it covers, so the share falls from the
        1-in-10 to the 1-in-500-year map; what stays outside even the 1-in-500 map is water the map does
        not model.
      </p>

      <h2 className="ev-h2"><span className="ev-kicker">Read with care</span>What this cannot tell you</h2>
      <ul className="ev-limits">{data.limits.map((t, i) => <li key={i}>{boldOnly(t)}</li>)}</ul>

      <footer className="ev-footer">
        <p><b>Sources.</b></p>
        <ul>{data.sources.map((s, i) => <li key={i}>{s}</li>)}</ul>
        {data.attribution && <p>{data.attribution}</p>}
        <p>
          Every number in this view is read from the team's computed tables by a script; none is typed
          by hand, except the legal date. Built {data.built || "n/a"} · {data.team}
        </p>
      </footer>
    </div>
  );
}

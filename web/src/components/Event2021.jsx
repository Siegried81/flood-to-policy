import React, { useEffect, useMemo, useRef, useState } from "react";
import { getEvent2021, getInteractive, getInteractiveIndex } from "../api.js";

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

// Nearest modelled-depth class for a clicked point: read the overlay PNG's pixel
// and match its colour to the legend. The depth PNG is same-origin, so its pixels
// are readable. Returns a label, or a "dry" note where the map is transparent.
function depthClassAt(canvas, depth, latlng) {
  const [[south, west], [north, east]] = depth.bounds;
  const x = Math.round(((latlng.lng - west) / (east - west)) * canvas.width);
  const y = Math.round(((north - latlng.lat) / (north - south)) * canvas.height);
  if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) return "outside the modelled area";
  const [r, g, b, a] = canvas.ctx.getImageData(x, y, 1, 1).data;
  if (a < 40) return "dry or not modelled here";
  let best = null, bestD = Infinity;
  for (const c of depth.classes) {
    const cr = parseInt(c.colour.slice(1, 3), 16);
    const cg = parseInt(c.colour.slice(3, 5), 16);
    const cb = parseInt(c.colour.slice(5, 7), 16);
    const d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2;
    if (d < bestD) { bestD = d; best = c.label; }
  }
  return best;
}

function loadDepthCanvas(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth;
      cv.height = img.naturalHeight;
      const ctx = cv.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(img, 0, 0);
      resolve({ ctx, width: cv.width, height: cv.height });
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

// The zoomable enhancement: Esri satellite tiles, the observed flood outline and
// the modelled 1-in-100 depth, with a click-for-depth readout. Leaflet and the
// per-place files load on demand; if either the files or the tiles cannot be
// fetched (offline), it says so and the baked satellite image stays the fallback.
function InteractiveMap({ place }) {
  const ref = useRef(null);
  const [status, setStatus] = useState("loading");
  const [readout, setReadout] = useState(null);
  const [legend, setLegend] = useState(null);

  useEffect(() => {
    let map = null;
    let canceled = false;
    (async () => {
      const data = await getInteractive(place.key);
      if (canceled) return;
      if (!data) { setStatus("unavailable"); return; }
      let L;
      try {
        L = (await import("leaflet")).default;
        await import("leaflet/dist/leaflet.css");
      } catch {
        setStatus("unavailable");
        return;
      }
      if (canceled || !ref.current) return;
      map = L.map(ref.current, { scrollWheelZoom: true });
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { attribution: "Imagery © Esri, Maxar, Earthstar Geographics", maxZoom: 18 },
      ).addTo(map);
      map.fitBounds(data.aoi_bounds);
      let depthCanvas = null;
      if (data.depth && data.depthUrl) {
        L.imageOverlay(data.depthUrl, data.depth.bounds, { opacity: 0.8 }).addTo(map);
        depthCanvas = await loadDepthCanvas(data.depthUrl);
        if (!canceled) setLegend(data.depth.classes);
      }
      if (data.flood) {
        L.geoJSON(data.flood, { style: { color: "#f06414", weight: 2, fillOpacity: 0 } }).addTo(map);
      }
      map.on("click", (e) => {
        setReadout(depthCanvas ? depthClassAt(depthCanvas, data.depth, e.latlng) : null);
      });
      if (!canceled) setStatus("ready");
    })();
    return () => {
      canceled = true;
      if (map) map.remove();
    };
  }, [place.key]);

  if (status === "unavailable") {
    return (
      <div className="ev-nomap">
        The interactive map needs a connection; the satellite image stays available offline.
      </div>
    );
  }
  return (
    <div className="ev-leaflet-wrap">
      <div ref={ref} className="ev-leaflet" />
      {status === "loading" && <p className="ev-small">Loading the interactive map…</p>}
      {legend && (
        <ul className="ev-depth-legend">
          <li className="ev-depth-title">Modelled 1-in-100 depth</li>
          {legend.map((c) => (
            <li key={c.label}><span className="ev-sw" style={{ background: c.colour }} />{c.label}</li>
          ))}
        </ul>
      )}
      <p className="ev-small">
        {readout
          ? <>Clicked point: <b>{readout}</b>.</>
          : "Click the map to read the modelled 1-in-100-year depth. Orange outline: the water Copernicus saw in July 2021."}
      </p>
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
        {m.credit && (
          <text x={w * 0.985} y={h - fs * 0.5} textAnchor="end" fontSize={fs * 0.85} fill="#fff"
                style={{ paintOrder: "stroke", stroke: "#00000088", strokeWidth: 3 }}>
            {m.credit}
          </text>
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
      {place.action && (
        <div
          style={{
            marginTop: "0.8rem",
            padding: "0.7rem 0.9rem",
            borderLeft: "3px solid #0b4f9c",
            background: "rgba(11,79,156,0.07)",
            borderRadius: "3px",
          }}
        >
          {place.action.priority && (
            <p style={{ margin: "0 0 0.45rem" }}><b>Evacuate first? (priority)</b> {place.action.priority}</p>
          )}
          <p style={{ margin: "0 0 0.45rem" }}><b>Can we shelter them? (Q3)</b> {place.action.shelter}</p>
          <p style={{ margin: "0 0 0.45rem" }}><b>Which lever? (Q4)</b> {place.action.lever}</p>
          <p className="ev-small" style={{ margin: "0 0 0.45rem" }}><b>Done since 2021 (Q2):</b> {place.action.since}</p>
          <p className="ev-small" style={{ margin: 0, opacity: 0.8 }}>Priority weights are the team's choice, not the AI's.</p>
        </div>
      )}
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
      {/* A bar from the most to the least frequent flood, one notch per period
          in the table, so the nesting reads left to right — the same control as
          the Europe view. */}
      <label className="rp-bar">
        <span>Return period: <b>1-in-{rp} years</b></span>
        <input
          type="range"
          aria-label="Return period"
          min={0}
          max={chart.return_periods.length - 1}
          step={1}
          value={Math.max(0, chart.return_periods.indexOf(rp))}
          onChange={(e) => setRp(chart.return_periods[Number(e.target.value)])}
        />
        <span className="rp-ticks">
          {chart.return_periods.map((p) => (
            <span key={p}>{p}</span>
          ))}
        </span>
      </label>
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

function Decision({ decision }) {
  if (!decision) return null;
  return (
    <section
      aria-label="The decision"
      style={{
        margin: "1.6rem 0",
        padding: "1rem 1.25rem",
        borderLeft: "4px solid #f0a030",
        background: "rgba(240,160,48,0.09)",
        borderRadius: "4px",
      }}
    >
      <h2 className="ev-h2" style={{ marginTop: 0 }}>
        <span className="ev-kicker">The decision</span>
        {decision.lead}
      </h2>
      {decision.actor && (
        <p className="ev-small" style={{ marginTop: "-0.3rem" }}>{decision.actor}</p>
      )}
      <ol style={{ margin: "0.6rem 0 0", paddingLeft: "1.2rem", lineHeight: 1.5 }}>
        {(decision.points || []).map((p, i) => (
          <li key={i} style={{ marginBottom: "0.5rem" }}>{p}</li>
        ))}
      </ol>
      {decision.before && decision.before.length > 0 && (
        <>
          <h3 style={{ margin: "1rem 0 0.4rem" }}>Before the water: from the forecast to the first drop</h3>
          <table className="ev-recos">
            <thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>
            <tbody>
              {decision.before.map((b, i) => (
                <tr key={i}><td><b>{b.when}</b></td><td>{b.who}</td><td>{b.what}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// One cross-border number: the whole border area at once, not three separate ones.
function Combined({ combined }) {
  if (!combined) return null;
  return (
    <p className="ev-combined">
      Across the three countries the first maps reached <b>{combined.buildings_shown}</b> buildings and{" "}
      <b>{combined.residents_shown}</b> residents — and <b>{nb(combined.share_shown)}</b> of those people lived
      outside the 1-in-100-year flood zone.
    </p>
  );
}

// The companion to the by-people chart: was the map right, read off the flooded area itself.
function Agreement({ rows }) {
  if (!rows || !rows.length) return null;
  return (
    <>
      <h3 className="ev-sub">Was the map right, by area?</h3>
      <table className="ev-agree">
        <thead>
          <tr><th>Country</th><th>Inside the 1-in-100 zone</th><th>1-in-500 only</th><th>Outside both maps</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.country}>
              <td>{r.name}</td><td>{nb(r.in100_shown)}</td><td>{nb(r.only500_shown)}</td><td>{nb(r.outside_shown)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ev-small">
        The share of the observed flood <b>area</b> (first maps) inside the 1-in-100-year zone, in the 1-in-500
        zone only, or outside both — the cell-weighted agreement with the JRC map. The chart above counts people;
        this counts flooded ground, so a place with much water but few residents still shows how much the map
        missed. “Outside both” mixes flooding beyond the modelled hazard with rivers too small to be modelled
        (catchment below the ~150 km² floor).
      </p>
    </>
  );
}

// The decision-facing warnings: plain do/don't, held before acting on the numbers.
function Warnings({ warnings }) {
  if (!warnings || !warnings.length) return null;
  return (
    <section className="ev-warnbox" aria-label="Read before acting">
      <p className="ev-warnhead">Before you act on these numbers</p>
      <ul>{warnings.map((w, i) => <li key={i}>{boldOnly(w)}</li>)}</ul>
    </section>
  );
}

function Recommendations({ recommendations }) {
  if (!recommendations || !recommendations.rows?.length) return null;
  return (
    <>
      <h2 className="ev-h2"><span className="ev-kicker">What we recommend</span>Two before the rain, one by the {recommendations.review_date} plan review</h2>
      <table className="ev-recos">
        <thead><tr><th>Action</th><th>Who, by when</th><th>Instrument, cost</th></tr></thead>
        <tbody>
          {recommendations.rows.map((r, i) => (
            <tr key={i}><td>{boldOnly(r.what)}</td><td>{r.who}</td><td>{r.how}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function NextSteps({ steps }) {
  if (!steps || !steps.length) return null;
  return (
    <>
      <h2 className="ev-h2"><span className="ev-kicker">Next steps on the ground</span>What to do next, grounded in the gaps above</h2>
      <table className="ev-recos">
        <thead><tr><th>Next step</th><th>Who, by when</th><th>The evidence it rests on</th></tr></thead>
        <tbody>
          {steps.map((s, i) => (
            <tr key={i}><td>{boldOnly(s.what)}</td><td>{s.who}</td><td>{s.basis}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Since({ since }) {
  if (!since || !since.length) return null;
  return (
    <>
      <h2 className="ev-h2"><span className="ev-kicker">Context</span>What has been done since July 2021</h2>
      <div className="ev-since">
        {since.map((s, i) => (
          <div key={i} className="ev-sincereg">
            <h3 className="ev-sub">{s.region}</h3>
            <ul>{s.points.map((p, j) => <li key={j}>{boldOnly(p)}</li>)}</ul>
          </div>
        ))}
      </div>
    </>
  );
}

export default function Event2021() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [key, setKey] = useState(null);
  const [showWater, setShowWater] = useState(false);
  const [interactiveKeys, setInteractiveKeys] = useState([]);
  const [showInteractive, setShowInteractive] = useState(false);

  useEffect(() => {
    getEvent2021()
      .then((d) => {
        setData(d);
        setKey(d.places?.[0]?.key ?? null);
      })
      .catch((e) => setError(e.message));
    getInteractiveIndex().then(setInteractiveKeys);
  }, []);

  // Back to the baked image whenever the place changes, so a toggle is per place.
  useEffect(() => { setShowInteractive(false); }, [key]);

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
      <Combined combined={data.combined} />
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
            {interactiveKeys.includes(place.key) && (
              <div className="ev-maptoggle" role="group" aria-label="Map mode">
                <button type="button" className={!showInteractive ? "on" : ""} aria-pressed={!showInteractive} onClick={() => setShowInteractive(false)}>Satellite image</button>
                <button type="button" className={showInteractive ? "on" : ""} aria-pressed={showInteractive} onClick={() => setShowInteractive(true)}>Interactive map</button>
              </div>
            )}
            {showInteractive && interactiveKeys.includes(place.key) ? (
              <InteractiveMap place={place} />
            ) : (
              <>
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
              </>
            )}
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
      <Agreement rows={data.agreement} />

      <Warnings warnings={data.warnings} />
      <Decision decision={data.decision} />
      <Recommendations recommendations={data.recommendations} />
      <NextSteps steps={data.next_steps} />
      <Since since={data.since} />
      {data.conclusion && (
        <>
          <h2 className="ev-h2"><span className="ev-kicker">In one paragraph</span>Conclusion</h2>
          <p className="ev-conclusion">{data.conclusion}</p>
        </>
      )}

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

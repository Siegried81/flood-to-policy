// Thin fetch wrappers around the FastAPI backend (see api/main.py).
// Everything goes through one `request` so an error always arrives as an Error
// with the server's own detail message, rather than as a silent undefined that
// surfaces three components later.

async function request(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d) => d.msg).join("; ");
    } catch {
      /* non-JSON error body: keep the status line */
    }
    throw new Error(detail);
  }
  return resp.json();
}

// True in a static build (`VITE_STATIC=1 npm run build`): no API behind the
// page, so only views that run from files shipped in dist/ are offered.
export const STATIC_BUILD = import.meta.env.VITE_STATIC === "1";

// A static build reads the API's own answers, frozen into web/public/europe/ by
// `scripts/export_europe_web.py`, resolved against the page base so a sub-path
// deployment finds them too.
const staticFile = (name) => request(`${import.meta.env.BASE_URL}europe/${name}`);

// GISCO's NUTS 2024 regions at 1:20 million, fetched by the viewer's browser
// from GISCO itself (it allows any origin). The repository and the Space never
// hold a copy: the GISCO terms do not let a public repository pass the geometry
// on (data/processed/DATA_NOTICE.md). Renamed to the two properties the map
// joins on, as `scripts/build_geometry.py` does for the local file.
const GISCO_NUTS3 =
  "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_20M_2024_4326_LEVL_3.geojson";

async function giscoRegions() {
  const resp = await fetch(GISCO_NUTS3);
  if (!resp.ok) throw new Error(`GISCO boundaries unavailable (${resp.status})`);
  const collection = await resp.json();
  return {
    type: "FeatureCollection",
    features: collection.features.map((f) => ({
      type: "Feature",
      properties: { nuts_id: f.properties.NUTS_ID, name: f.properties.NAME_LATN },
      geometry: f.geometry,
    })),
  };
}

const post = (path, body, headers = {}) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });

export const getMeta = () => (STATIC_BUILD ? staticFile("meta.json") : request("/api/meta"));

// Static: no period means the rarest one, as the server would pick.
export async function getExposure(returnPeriod) {
  if (STATIC_BUILD) {
    const period = returnPeriod ?? (await getMeta()).return_periods.at(-1);
    return staticFile(`exposure_rp${period}.json`);
  }
  return request(returnPeriod == null ? "/api/exposure" : `/api/exposure?return_period=${returnPeriod}`);
}

export const getGeometry = () => (STATIC_BUILD ? giscoRegions() : request("/api/geometry"));

// A SECOND table, fetched separately and deliberately never merged into the
// exposure rows. The vulnerability index is a weighted mean over whichever
// numeric columns are offered, so a climate percentage or a basin share carried
// on an exposure row would be one selection away from becoming a term in a
// vulnerability score. The response also carries `climate_periods`, which is the
// only thing that says what a period's figures are allowed to claim.
export const getContext = () =>
  STATIC_BUILD ? staticFile("context.json") : request("/api/context");

// `returnPeriod` is sent rather than left out. The table holds one row per region
// per return period, so a ranking is always a ranking of one scenario; omitting
// it hands the choice to the server, which then names the period it used in the
// response. Either way the panel reads the period off the result, never off its
// own state, so a figure is never labelled with a scenario it is not from.
export async function getVulnerability(indicators, perturbation, topN, returnPeriod) {
  if (!STATIC_BUILD) {
    return post("/api/vulnerability", {
      indicators,
      perturbation,
      top_n: topN,
      return_period: returnPeriod ?? null,
    });
  }
  // Precomputed for every indicator subset at one perturbation and one top N
  // (scripts/export_europe_web.py). Any other setting says so rather than
  // answering with the wrong settings.
  const period = returnPeriod ?? (await getMeta()).return_periods.at(-1);
  const frozen = await staticFile(`vulnerability_rp${period}.json`);
  if (perturbation !== frozen.perturbation || topN !== frozen.top_n) {
    throw new Error(`The static demo has the ranking at ±${frozen.perturbation * 100}% and top `
      + `${frozen.top_n} only. Run the app locally for other settings.`);
  }
  const answer = frozen.answers[[...indicators].sort().join("+")];
  if (!answer) throw new Error("This indicator set is not in the static demo.");
  return answer;
}

export const search = (q, k = 5) =>
  request(`/api/search?q=${encodeURIComponent(q)}&k=${k}`);

// The period on screen travels with the question, so the model reads the scenario
// the reader is looking at.
export const draft = (question, returnPeriod) =>
  post("/api/draft", { question, return_period: returnPeriod ?? null });

// Fetched rather than hardcoded in the panel: the list lives in
// `src/translate.py`, and a copy in the client would drift the moment a language
// is added. English is absent because it is the source.
export const getLanguages = () => request("/api/languages");

// A translation that changed a figure or moved a citation comes back as 422, so
// it arrives here as a thrown Error carrying the server's sentence - never as a
// 200 with a flag the caller could ignore and render anyway.
export const translate = (text, language) =>
  post("/api/translate", { text, language });

// The only call that writes to the brief. Kept separate from `draft` on purpose:
// generating and approving are different acts, and the API makes that structural
// rather than a matter of discipline.
//
// The token, when the server asks for one, is typed by the person approving and
// sent per call. It is never built into the bundle: a secret in the JavaScript
// is a secret every visitor of the page holds.
export const approve = (text, token) =>
  post("/api/approve", { text }, token ? { "X-Approve-Token": token } : {});

// What this deployment allows (GET /api/config): in the hosted demo the model
// and write routes answer 403, and the UI greys them instead of failing on click.
export const getConfig = () => request("/api/config");


// The July 2021 story. The static file Vite copied from web/public/ comes
// first, resolved against the page base so a sub-path deployment
// (VITE_BASE=/flood-to-policy/) finds it too; the API route is the fallback for
// a server whose dist/ was built before the file existed. A static build has no
// fallback to try.
export async function getEvent2021() {
  const file = `${import.meta.env.BASE_URL}event_2021_web.json`;
  try {
    const resp = await fetch(file);
    if (resp.ok && (resp.headers.get("content-type") || "").includes("json")) {
      return await resp.json();
    }
  } catch {
    /* fall through to the API */
  }
  if (STATIC_BUILD) {
    throw new Error("event_2021_web.json is missing from this build. Run "
      + "`python scripts/export_event_web.py`, then rebuild.");
  }
  return request("/api/event2021");
}

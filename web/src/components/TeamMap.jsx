import React, { useEffect, useState } from "react";

// Team 9's four-scene map, built in team9/map.py and shipped as a single
// self-contained HTML file under web/public/team9/. Vite copies public/ into
// dist/ as is, so the same relative path works behind the FastAPI mount (Docker,
// port 8001), on the HF Static Space and on surge.
//
// An iframe rather than a port to React: the file is Folium output with its own
// Leaflet build and scene controls, and it is the team's work, kept as they made
// it. App.jsx renders this only while the tab is open; it is the first view, so
// the 37 MB page is fetched when the app opens.
const MAP_URL = `${import.meta.env.BASE_URL}team9/flood_map.html`;

// A Git LFS pointer is about 130 bytes of text; the real map is tens of MB.
// Served in place of the file, the pointer shows as a blank frame.
const MIN_MAP_BYTES = 1024;

export default function TeamMap() {
  const [missing, setMissing] = useState(false);

  // A HEAD request, so the size is learnt without downloading the map. A host
  // that sends no content-length leaves the frame shown: only a measured tiny
  // file counts as missing.
  useEffect(() => {
    fetch(MAP_URL, { method: "HEAD" })
      .then((r) => {
        const size = Number(r.headers.get("content-length"));
        setMissing(!r.ok || (Number.isFinite(size) && size > 0 && size < MIN_MAP_BYTES));
      })
      // An unreachable host is not a missing map, so the frame stays, but the
      // failure is logged rather than swallowed.
      .catch((e) => console.warn("Team 9 map: HEAD request failed", e));
  }, []);

  return (
    <section className="team-map">
      <p className="caption">
        Team 9's interactive map: four scenes, from what the satellites saw to where to act first.
        It's a large page and can take a few seconds to load.{" "}
        <a href={MAP_URL} target="_blank" rel="noopener">Open it full screen</a>
      </p>
      {missing && (
        <p className="refusal">
          The map file is missing or is only a placeholder (a Git LFS pointer). Fetch the
          real file with <code>git lfs pull</code> or rebuild it with team9/map.py.
        </p>
      )}
      <iframe className="team-map-frame" src={MAP_URL} title="Team 9 map of the July 2021 floods" />
    </section>
  );
}

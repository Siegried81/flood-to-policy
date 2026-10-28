import React, { useMemo, useState } from "react";

/**
 * An SVG choropleth drawn straight from GeoJSON — no tile provider, no API key.
 *
 * The usual reflex is Leaflet over OpenStreetMap tiles, which means the map stops
 * working the moment the venue Wi-Fi does. Projecting the polygons ourselves and
 * drawing paths costs ~60 lines and the map then renders offline, which is the
 * difference between a demo and a demo that survives the room.
 *
 * The projection is Lambert azimuthal equal-area centred on 52N 10E, the
 * projection of EPSG:3035, so this map draws the same shapes as src/svgmap.py
 * and the brief. Nothing is computed from the projected coordinates: every
 * number arrives already aggregated from the server, which worked in EPSG:3035.
 * This is purely how the shapes get onto the screen.
 */

// Sequential, colourblind-safe (ColorBrewer YlOrRd). A diverging ramp would be
// wrong: exposure has a meaningful zero and no meaningful midpoint, so a
// two-ended scale would invent a threshold the data does not have.
const RAMP = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"];
const NO_DATA = "#d9d9d9";

// Regions drawn but kept OUT of the frame, mirrored from src/svgmap.py: the
// Canaries, Madeira, the Azores, the French overseas regions and Svalbard. With
// them in the extent the viewBox spans 119 x 102 degrees against 69 x 37
// without - 4.8 times the area, measured on regions.geojson -
// and the continent shrinks to a strip in the top right. They are still drawn (off
// frame) and counted in the caption, never dropped from the data.
const OUTERMOST = ["FRY", "PT20", "PT30", "ES70", "NO0B"];
const isOutermost = (id) => OUTERMOST.some((prefix) => String(id ?? "").startsWith(prefix));

/**
 * Lambert azimuthal equal-area forward projection on a sphere: [lon, lat] in
 * degrees to [x, y] in metres, with EPSG:3035's centre and false origin.
 *
 * Plain longitude/latitude would stretch Europe east-west (the in-frame extent
 * is 1.89 times wider than tall in degrees against 1.16 in EPSG:3035) and the
 * React map would disagree with the brief's map. The sphere (R = 6371007 m,
 * GRS80's authalic radius) stands in for the GRS80 ellipsoid because the output
 * only feeds a fitted viewport: the shapes differ by a fraction of a percent,
 * and a geodesy library would be a dependency for nothing. Exported so the
 * projection can be checked against pyproj outside the component.
 */
const LAEA_R = 6371007;
const LAEA_LAT0 = (52 * Math.PI) / 180;
const LAEA_LON0 = (10 * Math.PI) / 180;
export function laea([lon, lat]) {
  const phi = (lat * Math.PI) / 180;
  const dLambda = (lon * Math.PI) / 180 - LAEA_LON0;
  const cosC =
    Math.sin(LAEA_LAT0) * Math.sin(phi) +
    Math.cos(LAEA_LAT0) * Math.cos(phi) * Math.cos(dLambda);
  // The antipode of the centre has no image; nothing in Europe is near it.
  const k = Math.sqrt(2 / (1 + cosC));
  return [
    4321000 + LAEA_R * k * Math.cos(phi) * Math.sin(dLambda),
    3210000 +
      LAEA_R * k *
        (Math.cos(LAEA_LAT0) * Math.sin(phi) -
          Math.sin(LAEA_LAT0) * Math.cos(phi) * Math.cos(dLambda)),
  ];
}

/** Project every ring once, so the extent and the paths read the same points. */
function projectedRingsOf(geometry) {
  return ringsOf(geometry).map((ring) => ring.map(laea));
}

/** Quantile breaks, so the classes carry roughly equal counts.
 *
 * Equal-interval breaks on a long-tailed distribution — which exposure always is,
 * a few regions carrying most of it — put 95% of regions in the first class and
 * produce a map that looks uniformly empty. Quantiles show the ranking the brief
 * is actually about. Say which you used: the choice changes what the reader sees.
 */
function quantileBreaks(values, classes) {
  const sorted = [...values].filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!sorted.length) return [];
  return Array.from({ length: classes - 1 }, (_, i) =>
    sorted[Math.floor(((i + 1) / classes) * (sorted.length - 1))]
  );
}

function colourFor(value, breaks) {
  if (!Number.isFinite(value)) return NO_DATA;
  let i = 0;
  while (i < breaks.length && value > breaks[i]) i += 1;
  return RAMP[i];
}

/** Flatten a GeoJSON geometry to arrays of [lon, lat] rings. */
function ringsOf(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

/** Default value formatter; App passes a percent formatter for shares. */
const plain = (v) => v.toLocaleString();

/**
 * `format` turns a value into its display text for both the legend and the
 * tooltip, so a share reads "4.2%" in both places rather than "0.04" in one.
 */
export default function Choropleth({ geojson, values, valueKey, idKey, label, format = plain }) {
  const [hover, setHover] = useState(null);

  const { paths, breaks, bounds, offFrame } = useMemo(() => {
    const features = geojson?.features ?? [];
    const numbers = features.map((f) => values.get(f.properties?.[idKey]));
    const breaks = quantileBreaks(numbers, RAMP.length);

    // One pass for the extent: the viewBox has to fit the data, not a hard-coded
    // bounding box, so the same component works for Europe or for one valley.
    let [minX, minY, maxX, maxY] = [Infinity, Infinity, -Infinity, -Infinity];
    let offFrame = 0;
    const projected = features.map((feature) => projectedRingsOf(feature.geometry));
    features.forEach((feature, index) => {
      if (isOutermost(feature.properties?.[idKey])) {
        offFrame += 1;
        return;
      }
      for (const ring of projected[index]) {
        for (const [x, y] of ring) {
          if (x < minX) minX = x;
          if (y < minY) minY = y;
          if (x > maxX) maxX = x;
          if (y > maxY) maxY = y;
        }
      }
    });
    const paths = features.map((feature, index) => {
      const id = feature.properties?.[idKey];
      const d = projected[index]
        .map((ring) =>
          ring
            // y is negated because SVG's y axis grows downward while northing
            // grows upward — without this the map is upside down. Whole metres
            // are ample: one unit is a millionth of the frame.
            .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(0)} ${(-y).toFixed(0)}`)
            .join(" ") + " Z"
        )
        .join(" ");
      return { id, d, value: values.get(id), name: feature.properties?.name ?? id };
    });
    return { paths, breaks, offFrame, bounds: [minX, -maxY, maxX - minX, maxY - minY] };
  }, [geojson, values, idKey]);

  if (!geojson) return null;

  return (
    <figure className="choropleth">
      <svg viewBox={bounds.join(" ")} role="img" aria-label={label}>
        {paths.map((p) => (
          <path
            key={p.id}
            d={p.d}
            fill={colourFor(p.value, breaks)}
            className={hover === p.id ? "region hot" : "region"}
            onMouseEnter={() => setHover(p.id)}
            onMouseLeave={() => setHover(null)}
          >
            <title>
              {p.name}: {Number.isFinite(p.value) ? format(p.value) : "not measured"}
            </title>
          </path>
        ))}
      </svg>
      <figcaption>
        <span className="legend">
          {RAMP.map((colour, i) => (
            <span key={colour} className="swatch" style={{ background: colour }}>
              <em>{i < breaks.length ? `≤${format(breaks[i])}` : "max"}</em>
            </span>
          ))}
          <span className="swatch" style={{ background: NO_DATA }}>
            <em>not measured</em>
          </span>
        </span>
        {label} · quantile classes, so the map shows the ranking rather than a long
        tail. “Not measured” is a region the hazard raster does not cover — not a
        region with nobody exposed.
        {offFrame > 0 && (
          <>
            {" "}
            {offFrame} outermost regions (Canaries, Madeira, Azores, French overseas,
            Svalbard) are outside this frame; they are in every figure and in the table.
          </>
        )}
        {/* Required by the GISCO terms on any map drawn from the NUTS boundaries. */}
        <span className="credit"> © EuroGeographics for the administrative boundaries.</span>
      </figcaption>
    </figure>
  );
}

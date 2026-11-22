// Single source: data/processed/event_2021_web.json (tracked, written by
// scripts/export_event_web.py). Vite serves/copies web/public/, so mirror it there
// before dev and build. A missing source only warns: the app reports it at run time.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../data/processed/event_2021_web.json");
const dst = resolve(here, "../public/event_2021_web.json");

if (existsSync(src)) {
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(src, dst);
} else {
  console.warn(`copy-event: ${src} not found, skipping`);
}

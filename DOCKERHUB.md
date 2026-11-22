# flood-to-policy

- **Source, Dockerfile, issues:** https://github.com/Siegried81/flood-to-policy
- **Also on:** GitHub Container Registry, `ghcr.io/siegried81/flood-to-policy`
- **Architecture:** `linux/amd64`
- **Tags:** `latest` (current `main`), `X.Y.Z` and `X` (from a `vX.Y.Z` git tag), `sha-xxxxxxx` (one commit)

## What is it?

Flood-risk policy toolkit built for the European AI Challenge 2026 (JRC x FARI): the
July 2021 floods in Belgium, Germany and the Netherlands read against the European
flood hazard map, exposure per NUTS3 region, and a policy brief drafted with an LLM and
signed by a human.

The image holds the code, the built React UI and the four small data files committed to
the repository (the two frozen tables, the July 2021 story and their licence notice):
enough to see the project with nothing cloned and nothing mounted. Rebuilding the tables
needs the full `data/` folder. It does not contain the test suite or Team 9's map.

## Use

```bash
# React UI and JSON API, the one to look at
docker run -d -p 127.0.0.1:8001:8001 siegried/flood-to-policy \
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8001      # http://localhost:8001

# Streamlit (the default command)
docker run -d -p 127.0.0.1:8501:8501 siegried/flood-to-policy    # http://localhost:8501
```

With a clone and its data add `-v "$PWD/data:/app/data"` (read-write: caches and the
approved brief are written there) and run it from the repository folder: the mount
replaces `/app/data` entirely.

## Environment variables

None is required. Secrets are never baked in: pass them with `-e NAME=value` or
`--env-file .env`.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OLLAMA_URL` | language model, asked in that order (optional) |
| `RDH_BEARER_TOKEN` | Risk Data Hub token; expires after 10 h |
| `FLOOD_APPROVE_TOKEN` | secret `POST /api/approve` requires as `X-Approve-Token`; unset, only loopback callers (or the Docker gateway, with the port published on 127.0.0.1) may approve |

## Licence

Code: MIT. The data keeps its own licences (`/app/data/processed/DATA_NOTICE.md`).

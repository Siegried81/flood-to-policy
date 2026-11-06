# flood-to-policy

## Quick reference

- **Source code, Dockerfile, issues:** https://github.com/Siegried81/flood-to-policy
- **Maintained by:** Siegried81
- **Also on:** GitHub Container Registry, `ghcr.io/siegried81/flood-to-policy`
- **Architecture:** `linux/amd64`

## Supported tags

- `latest`: the current `main` branch
- `X.Y.Z` and `X`: built when a `vX.Y.Z` git tag is pushed (none yet), the ones to pin for a stable deployment
- `sha-xxxxxxx`: one specific commit

## What is it?

Flood-risk policy toolkit built for the European AI Challenge 2026 (JRC x FARI): the July 2021 floods in Belgium, Germany and the Netherlands read against the European flood hazard map, flood exposure per NUTS3 region, and a policy brief drafted with an LLM and signed by a human.

The image is about 1.7 GB. It holds the code, the tests, the built React UI and the four small data files committed to the repository: the two frozen tables, the July 2021 story and their licence notice. That is enough to see the project with nothing cloned and nothing mounted. You get the July 2021 view, the Europe ranking, and the Europe map, whose region boundaries the browser fetches from Eurostat/GISCO. Rebuilding the tables needs the full `data/` folder (83 GiB on the author's machine, 70 of it HERA river discharge files).

Two UIs from the same image: the React UI with its JSON API on 8010, and Streamlit on 8501 (the default command).

## How to use this image

```bash
# the React UI and its JSON API, the one to look at
docker run -d -p 127.0.0.1:8010:8010 siegried/flood-to-policy \
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8010
# open http://localhost:8010

# Streamlit instead
docker run -d -p 127.0.0.1:8501:8501 siegried/flood-to-policy
# open http://localhost:8501
```

With a clone of the repository and its data, add `-v "$PWD/data:/app/data"` and run it from the repository folder. The mount replaces the image's `/app/data` entirely, so from the wrong folder you get an empty app.

## Environment variables

None are required to start the UI. Secrets are **never** baked into the image: pass
them at run time with `-e NAME=value` or `--env-file .env` (see `.env.example` in the repo).

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | LLM provider asked first (optional; `ANTHROPIC_MODEL` picks the model, Opus by default) |
| `GROQ_API_KEY` | LLM provider (optional: Ollama works offline) |
| `OLLAMA_URL` | Ollama server, e.g. `http://host.docker.internal:11434` |
| `RDH_BEARER_TOKEN` | Risk Data Hub token; expires after 10 h, so always pass it at run time |
| `FLOOD_APPROVE_TOKEN` | Shared secret `POST /api/approve` requires as `X-Approve-Token`; when unset, approval relies on the port being published on 127.0.0.1 only, as above |

## Volumes

- `/app/data`: datasets and caches, read-write (the cache and the approved brief are written there). Optional: without a mount, the image uses its four committed files.

## License

Code under MIT, see LICENSE in the source repository. The data, in the image or mounted, keeps its own licences (see `/app/data/processed/DATA_NOTICE.md`). As with any image, check that your use fits the licences of the software it contains.

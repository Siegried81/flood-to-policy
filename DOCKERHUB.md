# flood-policy-kit

## Quick reference

- **Source code, Dockerfile, issues:** https://github.com/Siegried81/flood-to-policy
- **Maintained by:** Siegried81
- **Also on:** GitHub Container Registry, `ghcr.io/siegried81/<image>`
- **Architecture:** `linux/amd64`

## Supported tags

- `latest`: the current `main` branch
- `X.Y.Z` and `X`: built when a `vX.Y.Z` git tag is pushed (none yet), the ones to pin for a stable deployment
- `sha-xxxxxxx`: one specific commit

## What is it?

Flood-risk policy toolkit for the European AI Challenge 2026 (JRC x FARI): a Streamlit map of flood exposure per NUTS3 region, a JSON API for a React UI, and an LLM-written policy brief.

Images from this repository:

- `flood-policy-kit`: code only (~2 GB); the data tree (~80 GiB, ~69 GiB of it HERA discharge files) is bind-mounted

## How to use this image

```bash
docker run -d -p 127.0.0.1:8501:8501 -v "$PWD/data:/app/data" siegried/flood-to-policy
# open http://localhost:8501

# JSON API instead of Streamlit
docker run -d -p 127.0.0.1:8010:8010 -v "$PWD/data:/app/data" siegried/flood-to-policy \
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8010
```

## Environment variables

None are required to start the UI. Secrets are **never** baked into the image: pass
them at run time with `-e NAME=value` or `--env-file .env` (see `.env.example` in the repo).

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | LLM provider asked first (optional; `ANTHROPIC_MODEL` picks the model, Opus by default) |
| `GROQ_API_KEY` | LLM provider (optional: Ollama works offline) |
| `OLLAMA_URL` | Ollama server, e.g. `http://host.docker.internal:11434` |
| `RDH_BEARER_TOKEN` | Risk Data Hub token; expires after 10 h, so always pass it at run time |
| `FLOOD_APPROVE_TOKEN` | Shared secret `POST /api/approve` requires as `X-Approve-Token`; unset, approval relies on the loopback-only publish above |

## Volumes

- `/app/data`: datasets and caches; read-write (cache + approved brief are written here)

## License

MIT, see the LICENSE file in the source repository. As with every image, it is
your responsibility to check that your use complies with the licenses of the
software it contains.

# Security policy

## Supported versions

This is a portfolio and training project. Only the latest commit on `main` is
maintained; fixes land there and nowhere else, including for any image tagged
`v*` on GHCR.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Use GitHub's private reporting instead: the **Security** tab of this repository,
then **Report a vulnerability**. If that button is not available, open an issue
titled "Security contact" with no details, and a private channel will be
arranged.

Include what you found, how to reproduce it, and what an attacker gains. You can
expect a first answer within seven days; a confirmed issue is fixed on `main`
and credited in the fix unless you prefer otherwise.

## Secrets

Every key and token is read from the shell environment or a local `.env` that
git ignores (the CDS scripts also accept `~/.cdsapirc`); `.env.example` lists
every key with an empty value (non-secret settings carry their defaults), except `EWDS_API_KEY`, which
`scripts/fetch_efas_july2021.py` documents itself. A credential that appears in
this repository's history is a vulnerability in its own right: report it the
same way, and it will be revoked rather than merely deleted.

## What is in scope here

- The kit runs offline on public data (JRC, Eurostat, EEA, Copernicus); it
  stores no personal data.
- Keys it may read: `ANTHROPIC_API_KEY`, `GROQ_API_KEY` (and `GROQ_API_KEY_2`), `LANGSMITH_API_KEY`, `NEWSAPI_KEY`, `RDH_BEARER_TOKEN`,
  `CDSAPI_KEY`, `EWDS_API_KEY` and the `FLOOD_APPROVE_TOKEN` shared secret.
  None is needed to run the demo offline.
- Run the API container with its port on loopback (`-p 127.0.0.1:8001:8001`,
  as `docker-compose.yml` does). Without a token, the API treats a private
  address inside plain Docker as this machine, because the host's own browser
  arrives from the bridge gateway; a port published on all interfaces would let
  the local network approve. Set `FLOOD_APPROVE_TOKEN` otherwise, and `HOSTED=1`
  for anything public.
- In scope: anything that makes the draft workflow publish text a human did not
  approve, a retrieved document that changes the model's instructions, or a
  fetch that bypasses `robots.txt` or the declared sources in
  `config/sources.yaml`.

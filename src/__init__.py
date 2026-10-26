"""Load `.env` once, before any module in this package reads an environment variable.

Every optional integration here is keyed off one variable - `GROQ_API_KEY` for
generation, `RDH_BEARER_TOKEN` for the Risk Data Hub, `LANGSMITH_*` for tracing,
`NEWSAPI_KEY` for the recency top-up - and each degrades to "unavailable" when
its variable is missing. Without this call, a `.env` that was filled in correctly
but never read is indistinguishable from one that is empty: the kit reports every
integration as unavailable and looks like a wrong-key problem. That is the worst
failure mode available, because it is silent and it points at the wrong cause.

Two deliberate choices:

**The path is explicit, not discovered.** `load_dotenv()` with no argument walks
up from the *current working directory*, so `streamlit run app/streamlit_app.py`
launched from anywhere but the repo root would silently find nothing. Anchoring
on this file makes the lookup independent of where the process was started.

**`override=False`, so a real shell variable beats the file.** That is what keeps
`RDH_BEARER_TOKEN=... python -m src.rdh` working for a token that expires every
ten hours, and it is why the test suite can `monkeypatch.setenv` / `delenv`
freely: the file never overwrites what a caller set on purpose.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

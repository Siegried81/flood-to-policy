"""Suite-wide guard: no test may reach a paid or tracing service with a real key.

`src/__init__.py` loads the project's `.env` on import, so a developer's real
keys are in `os.environ` for every test. `rag.complete` asks Claude first
whenever `ANTHROPIC_API_KEY` is set, and Groq whenever any `GROQ_API_KEY*` is,
so any test that exercises the provider chain without clearing them - the
`/api/ask` 502 test, a UI test that drafts a section - would spend paid credit
and pass or fail on the network. LangSmith is the same leak in the other
direction: with `LANGSMITH_TRACING` set, every LangGraph run in
`test_workflow.py` uploads its trace. CI has none of these, so clearing them
everywhere is also what makes a local run mean what a CI run means. A test that
wants a provider sets a fake key with `monkeypatch.setenv`.
"""

from __future__ import annotations

import pytest

from src.rag import GROQ_KEY_VARS

_CLEARED = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    *GROQ_KEY_VARS,
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
)


@pytest.fixture(autouse=True)
def _no_real_provider_keys(monkeypatch):
    for name in _CLEARED:
        monkeypatch.delenv(name, raising=False)

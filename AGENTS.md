# AGENTS.md — Working Agreement

## Quality Bar

- Fully typed: Pydantic (backend) and TypeScript (frontend). `tsc --noEmit` and lint must pass.
- `pytest`: rule engine (all five types), measurement, comparison, template loading, cache keys, API smoke tests.
- `scripts/make_sample_video.py` generates a 20–30 second synthetic video so everything runs without real footage.
- Validate uploads (type, size). Handle failed jobs, empty results, and unreadable videos with clear messages.
- Never log or return secrets. No auth, payments, or accounts.
- Every provider call goes through the cache and the cost log.
- Mark every place that needs the real Meta API with `TODO(meta)`.
- Keep changes small, explain them, do not refactor files not mentioned, ask before adding unlisted dependencies.
- Record important choices in `docs/DECISIONS.md`.

## Provider Discipline

- In **mock mode**, providers return deterministic data from the scenario file.
- In **meta mode**, `providers/meta.py` raises `NotImplementedError` until implemented.
- All numbers in findings come from tool code, never from the planner.

## Evidence First

A finding may only state a measurement that came from a tool, with its method
and uncertainty. No evidence → status is `unsure`.

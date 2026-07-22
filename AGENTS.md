# Agent instructions

Scope: reusable GitHub Actions orchestration.

- Workflows must be callable, read-only, deterministic, and minimally privileged.
- Do not duplicate product validation logic; invoke the caller's canonical command.
- Do not add deployment, release, source-authoring, or secret-consuming behavior without a separate accepted organization ADR.
- Do not accept arbitrary shell commands as workflow inputs.
- Production callers pin an immutable commit, not `main` or `master`.
- Run `python scripts/validate.py` before proposing changes.

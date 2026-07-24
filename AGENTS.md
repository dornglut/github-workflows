# Agent instructions

Scope: reusable GitHub Actions orchestration.

- Workflows must be callable, read-only, deterministic, and minimally privileged.
- Do not duplicate product validation logic; invoke the caller's canonical command.
- Do not add deployment, release, source-authoring, or secret-consuming behavior without a separate accepted organization ADR.
- Do not accept arbitrary shell commands, scripts, toolchains, runners, paths, inputs, or inherited secrets.
- Pin every external Action to a full commit SHA with an inline release comment maintained by Dependabot.
- Set checkout `persist-credentials: false` unless a separately accepted workflow requires publication authority.
- Production callers pin an immutable commit of this repository, not `main` or `master`.
- Treat toolchain, runner, cache, permissions, command, diagnostics, and Action dependency changes as caller-impacting.
- Run `python scripts/validate.py` before proposing changes.

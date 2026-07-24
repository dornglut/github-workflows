# Reusable workflow contract

A shared workflow may standardize runner selection, exact checkout, maintained toolchain installation, dependency caching, timeout, permissions, invocation of a repository-owned command, and bounded failure diagnostics.

It must not:

- redefine the caller's validation semantics;
- mutate source, issues, pull requests, branches, tags, releases, or packages;
- create diagnostic or generated files inside the caller checkout before repository validation completes;
- use `pull_request_target`;
- request write permissions;
- receive or inherit secrets unless a later accepted ADR authorizes a bounded use case;
- accept an arbitrary command, script, toolchain, runner, or working-directory input;
- hide validation failures or convert them into generated commits.

## Dependency and checkout contract

- every external Action is pinned to a full commit SHA;
- the same line records the intended release tag for human review and Dependabot updates;
- checkout uses a clean shallow fetch of the triggering caller revision;
- checkout sets `persist-credentials: false`;
- Action dependency updates arrive through reviewed pull requests;
- a reusable-workflow revision remains immutable for existing callers.

## Rust validation profile

The maintained Rust workflow has one fixed profile:

- GitHub-hosted Ubuntu runner;
- exact clean checkout with shallow history and no persisted credential;
- stable Rust with `rustfmt` and `clippy`;
- Rust 1.93.0 with `rustfmt` and `clippy` available for repository-owned MSRV checks;
- Cargo caching;
- `cargo +stable validate` as the only validation invocation;
- failure-only upload of an out-of-tree `validation.log` below `RUNNER_TEMP` with three-day retention;
- cleanup of the out-of-tree log on every result.

The workflow supplies the environment required by the current Dornglut Rust repositories. The caller's `.cargo/config.toml`, `xtask`, lockfiles, tests, documentation checks, policy checks, and clean-state proof remain the validation authority.

## Python documentation profile

The maintained Python workflow has one fixed profile:

- GitHub-hosted Ubuntu runner;
- exact clean checkout with shallow history and no persisted credential;
- `python scripts/validate.py` as the only validation invocation;
- no workflow inputs, inherited secrets, generated output, or diagnostic upload.

Caller workflows own event triggers, branch filters, concurrency, and any repository-specific permissions that are stricter than the shared baseline.

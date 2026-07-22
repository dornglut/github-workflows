# Reusable workflow contract

A shared workflow may standardize runner selection, exact checkout, maintained toolchain installation, dependency caching, timeout, permissions, invocation of a repository-owned command, and bounded failure diagnostics.

It must not:

- redefine the caller's validation semantics;
- mutate source, issues, pull requests, branches, tags, releases, or packages;
- use `pull_request_target`;
- request write permissions;
- receive or inherit secrets unless a later accepted ADR authorizes a bounded use case;
- accept an arbitrary command, script, toolchain, runner, or working-directory input;
- hide validation failures or convert them into generated commits.

## Rust validation profile

The maintained Rust workflow has one fixed profile:

- GitHub-hosted Ubuntu runner;
- exact clean checkout with shallow history;
- stable Rust with `rustfmt` and `clippy`;
- Rust 1.93.0 with `rustfmt` and `clippy` available for repository-owned MSRV checks;
- Cargo caching;
- `cargo +stable validate` as the only validation invocation;
- failure-only upload of `validation.log` with three-day retention;
- cleanup of the local log on every result.

The workflow supplies the environment required by the current Dornglut Rust repositories. The caller's `.cargo/config.toml`, `xtask`, lockfiles, tests, documentation checks, and policy checks remain the validation authority.

Caller workflows own event triggers, branch filters, concurrency, and any repository-specific permissions that are stricter than the shared baseline.

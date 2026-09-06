# Reusable workflow contract

A shared workflow may standardize runner selection, exact checkout, maintained toolchain installation, dependency caching, timeout, permissions, invocation of a repository-owned command, bounded failure diagnostics, and fixed out-of-tree review-artifact publication produced by that command.

It must not:

- redefine the caller's validation semantics;
- mutate source, issues, pull requests, branches, tags, releases, or packages;
- create diagnostic or generated files inside the caller checkout before repository validation completes;
- use `pull_request_target`;
- request write permissions;
- receive or inherit secrets unless a later accepted ADR authorizes a bounded use case;
- accept an arbitrary command, script, toolchain, runner, path, or working-directory input;
- hide validation failures or convert them into generated commits.

## Dependency and checkout contract

- every external Action is pinned to a full commit SHA;
- the same line records the intended release tag for human review and Dependabot updates;
- pull-request callers validate `github.event.pull_request.head.sha`, while `push` and `workflow_dispatch` callers validate `github.sha`; unsupported events or an empty revision fail before checkout;
- checkout explicitly selects that expected revision, then proves `git rev-parse HEAD` equals it before toolchain installation or repository validation;
- pull-request feature-head validation is distinct from validation of GitHub's synthetic merge result and does not claim an eventual squash-merge revision;
- checkout sets `persist-credentials: false`;
- Action dependency updates arrive through reviewed pull requests;
- a reusable-workflow revision remains immutable for existing callers.

## Rust validation profile

The maintained Rust workflow has one fixed profile:

- GitHub-hosted Ubuntu runner;
- exact clean checkout with shallow history and no persisted credential;
- stable Rust with `rustfmt` and `clippy`;
- each unique caller-declared `rust-version` value reported by Cargo metadata is installed with `rustfmt` and `clippy`; a caller that declares none receives no additional Rust toolchain;
- Cargo metadata discovery runs from an exact temporary archive under `RUNNER_TEMP`, so environment provisioning does not generate or update files in the caller checkout;
- Cargo caching;
- `cargo +stable validate` as the only validation invocation;
- compact success evidence naming the repository, event, expected and actual revisions, canonical command, and conclusion;
- the canonical validation process receives `REPOSITORY_REVIEW_ARTIFACT_DIR` pointing to the fixed `${RUNNER_TEMP}/repository-review-artifacts` directory; callers may optionally write human-review evidence there as part of their own validation semantics;
- after successful validation, that fixed directory is uploaded when populated as a seven-day `rust-repository-review-artifacts-<exact-revision>` review artifact; an empty directory produces no artifact and is not an error;
- up to 40 selected diagnostic lines and 160 final log lines on failure, with the complete out-of-tree log below `RUNNER_TEMP` retained in the `rust-repository-validation-diagnostics` artifact for three days;
- cleanup of the out-of-tree validation log on every result.

The workflow never generates caller-specific review evidence itself. It only provides the fixed out-of-tree destination and publishes caller-validation output after the canonical command succeeds. Review artifact publication does not alter the caller checkout or validation result and is not a second validation command.

The workflow supplies stable Rust plus caller-declared `rust-version` values required by checked-out Cargo metadata. The caller remains authoritative for whether an MSRV is declared, which version is declared, whether review evidence is generated, and whether or how canonical validation exercises those contracts. The caller's `.cargo/config.toml`, `xtask`, lockfiles, tests, documentation checks, policy checks, and clean-state proof remain the validation authority.

## Python documentation profile

The maintained Python workflow has one fixed profile:

- GitHub-hosted Ubuntu runner;
- exact clean checkout with shallow history and no persisted credential;
- `python scripts/validate.py` as the only validation invocation;
- the same compact success evidence and bounded failure diagnostics as the Rust profile, with the complete log retained for three days in `python-repository-validation-diagnostics`;
- no workflow inputs, inherited secrets, or generated output.

Caller workflows own event triggers, branch filters, concurrency, and any repository-specific permissions that are stricter than the shared baseline.

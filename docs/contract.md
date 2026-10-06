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
- pull-request callers validate `github.event.pull_request.head.sha`; `merge_group` callers validate the merge-group `github.sha`; `push` and `workflow_dispatch` callers validate `github.sha`; unsupported events or an empty revision fail before checkout;
- checkout explicitly selects that expected revision, then proves `git rev-parse HEAD` equals it before toolchain installation or repository validation;
- pull-request feature-head validation is distinct from `merge_group` integration validation: the former proves the reviewed feature head, while the latter proves GitHub's exact merge-group SHA against the queue's current integration state; neither is the eventual squash-merge revision;
- checkout sets `persist-credentials: false`;
- Action dependency updates arrive through reviewed pull requests;
- a reusable-workflow revision remains immutable for existing callers.

## Rust validation profile

The maintained Rust workflow has one fixed execution profile:

- GitHub-hosted Ubuntu runners;
- exact clean checkout with shallow history and no persisted credential;
- a checkout-only planning job that resolves and proves the expected caller revision before reading partition inventory;
- stable Rust with `rustfmt` and `clippy` on every validation runner;
- each unique caller-declared `rust-version` value reported by Cargo metadata is installed with `rustfmt` and `clippy`; a caller that declares none receives no additional Rust toolchain;
- Cargo metadata discovery runs from an exact temporary archive under `RUNNER_TEMP`, so environment provisioning does not generate or update files in the caller checkout;
- Cargo registry/download caching without restoring workspace `target/` artifacts, under an explicit source-fresh cache-policy generation that cannot reuse archives from the retired workspace-target policy;
- source-addressed Rust compiler-output caching through the reviewed sccache setup, with `CARGO_INCREMENTAL=0`, `SCCACHE_GHA_ENABLED=on`, and `RUSTC_WRAPPER=sccache` scoped to repository validation;
- no shared-workflow override of GitHub cache access mode or sccache GHA read/write mode; caller/event cache-token scope remains authoritative;
- `fail-fast: false` across partition validation so independent failures remain visible;
- one stable `Repository baseline` aggregate that succeeds only when planning and every required validation runner succeed;
- compact success evidence naming the repository, event, expected and actual revisions, effective canonical command, and conclusion, plus at most the final 40 validation-log lines as a bounded success summary;
- successful validation never streams or uploads the complete captured log;
- up to 40 selected diagnostic lines and 160 final log lines on failure, with a collision-free complete out-of-tree log below `RUNNER_TEMP` retained for three days;
- cleanup of out-of-tree validation logs on every result.

## Rust partition contract

A caller may place `validation-partitions.txt` at the repository root to expose
repository-owned execution partitions. Caller workflow YAML does not pass a partition
count or list.

When the manifest is absent, the generated validation matrix contains one `complete`
entry and invokes `cargo +stable validate`. When the manifest is present, it contains
one partition identifier per line and each validation runner invokes the same canonical
Cargo alias with `--partition <id>`.

The workflow treats manifest content as untrusted orchestration data:

- the manifest must be a regular UTF-8 file ending in a newline and no larger than 512 bytes;
- it contains between one and four unique identifiers;
- identifiers match `[a-z][a-z0-9-]{0,31}`;
- `complete` is reserved for the serial fallback;
- blank lines, surrounding whitespace, duplicates, malformed identifiers, symlinks, and oversized inventories fail planning;
- matrix runners revalidate their mode and identifier before constructing an argument array;
- identifiers are never evaluated as shell or accepted as commands, paths, runners, toolchains, scripts, working directories, or secrets.

The repository remains authoritative for partition membership and for proving that the
complete set of partitions is semantically equivalent to its complete canonical
invocation. The shared workflow does not infer lanes or decide that a repository check
may be omitted.

The planning job resolves and proves the exact caller revision once; every matrix
runner independently checks out and proves that same selected revision. No validation partition may rely on another partition's mutable workspace or
build artifacts for correctness. The aggregate `Repository baseline` fails when
planning fails or when required validation is failed, skipped, or cancelled.

Canonical validation must compile caller workspace artifacts from the checked-out exact source revision. Shared workspace `target/` artifacts are therefore not restored by the reusable workflow. The Cargo-data cache prefix is a cache-policy generation: any change that could alter which caller files are restored must use a new generation rather than sharing keys with an older policy. Compiler-cache reuse occurs only at individual rustc invocations through sccache; it must not restore Cargo fingerprint state, test executables, or another revision's workspace `target/` tree.

The workflow supplies stable Rust plus caller-declared `rust-version` values required by checked-out Cargo metadata. The caller remains authoritative for whether an MSRV is declared, which version is declared, and whether or how canonical validation exercises that version. The caller's `.cargo/config.toml`, `xtask`, lockfiles, tests, documentation checks, policy checks, partition manifest, and clean-state proof remain the validation authority.

## Python documentation profile

The maintained Python workflow has one fixed profile:

- GitHub-hosted Ubuntu runner;
- exact clean checkout with shallow history and no persisted credential;
- `python scripts/validate.py` as the only validation invocation;
- the same compact success evidence and bounded failure diagnostics as the Rust profile, with the complete log retained for three days in `python-repository-validation-diagnostics`;
- no workflow inputs, inherited secrets, or generated output.

Caller workflows own event triggers, branch filters, concurrency, and any repository-specific permissions that are stricter than the shared baseline.

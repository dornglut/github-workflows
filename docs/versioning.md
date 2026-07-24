# Versioning and adoption

Reusable workflows are source dependencies.

## Caller policy

Production callers pin an exact accepted commit:

```yaml
jobs:
  validate:
    uses: dornglut/github-workflows/.github/workflows/reusable-rust-cargo-validate.yml@<full-commit-sha>
```

Do not use `main` or `master`. Moving major-version references may be introduced only after a release and compatibility policy exists.

## Change policy

- additive orchestration changes require validation and documented caller impact;
- changing fixed Rust toolchains, command, runner, permissions, checkout behavior, cache behavior, Action dependencies, or diagnostics is compatibility-significant and requires caller migration review;
- breaking changes require a new workflow file or explicit migration plan;
- repository commands remain the behavioral compatibility boundary;
- deprecated workflows stay available until known callers migrate or an accepted decision authorizes removal.

External Action updates are proposed by Dependabot and reviewed like any other workflow change. A version comment on the same line as a full SHA records the intended release family and must be updated with the SHA.

## Current checkout generation

The workflow library uses `actions/checkout` v7.0.1 at reviewed commit `3d3c42e5aac5ba805825da76410c181273ba90b1`. This is a compatibility-significant dependency update from the v6 generation used by accepted revision `b6caad377102ca73794efaf734a65903b8efa829`.

Existing callers pinned to `b6caad377102ca73794efaf734a65903b8efa829` remain reproducible and are not silently migrated. The first caller adoption of the checkout-v7 workflow revision must be a separate exact-head PR that verifies checkout state, validation behavior, check naming, and diagnostics before broader adoption.

## Adoption sequence

1. merge and record the exact shared-workflow revision;
2. adopt it in one low-risk caller while preserving that repository's triggers and concurrency;
3. require exact-head caller CI;
4. compare behavior, check names, checkout state, and diagnostics with the former revision;
5. adopt in additional repositories through separate local pull requests;
6. retain the former immutable revision until known callers have migrated or explicitly accepted remaining on it.

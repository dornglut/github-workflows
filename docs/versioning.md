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
- changing the fixed Rust toolchains, command, runner, permissions, cache behavior, or diagnostic contract is compatibility-significant and requires a caller migration review;
- breaking changes require a new workflow file or explicit migration plan;
- repository commands remain the behavioral compatibility boundary;
- deprecated workflows stay available until known callers migrate or an accepted decision authorizes removal.

## Adoption sequence

1. merge and record the exact shared-workflow revision;
2. adopt it in one low-risk caller while preserving that repository's triggers and concurrency;
3. require exact-head caller CI;
4. compare behavior and diagnostics with the former local workflow;
5. adopt in additional repositories through separate local pull requests.

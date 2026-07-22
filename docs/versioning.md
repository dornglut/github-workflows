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
- breaking changes require a new workflow file or explicit migration plan;
- repository commands remain the compatibility boundary;
- deprecated workflows stay available until known callers migrate or an accepted decision authorizes removal.

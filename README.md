# Dornglut GitHub Workflows

This repository publishes reusable, read-only GitHub Actions orchestration for Dornglut repositories.

Shared workflows call repository-owned validation commands. They do not copy product-specific validation logic, modify implementation source, publish releases, or receive organization secrets.

## Reusable workflows

- [`reusable-rust-cargo-validate.yml`](.github/workflows/reusable-rust-cargo-validate.yml) resolves and proves the exact caller revision, discovers an optional bounded repository-owned `validation-partitions.txt` inventory, executes complete or partitioned canonical Rust validation on source-fresh isolated runners, preserves Cargo/sccache policy, and reports one fail-closed `Repository baseline` aggregate.
- [`reusable-python-repository-validate.yml`](.github/workflows/reusable-python-repository-validate.yml) checks out the verified caller revision and runs `python scripts/validate.py` with bounded failure diagnostics.

Third-party Actions are pinned to full commit SHAs with readable release comments. Dependabot proposes reviewed updates; tags and branches are not trusted as immutable workflow dependencies.

Callers own triggers, concurrency, and repository-specific branch rules. They pin an accepted immutable commit of this repository and must not reference `main` or `master`.

The normative [reusable workflow contract](docs/contract.md) distinguishes reviewed feature-head validation from synthetic merge-result validation and records the event-to-revision and diagnostics guarantees.

Canonical validation:

```text
python scripts/validate.py
```

## License

Current repository content is licensed under the [Apache License 2.0](LICENSE) (`Apache-2.0`). This organization-infrastructure repository does not use the separate commercial licensing path assigned to Dornglut product repositories. Third-party Actions remain governed by their own upstream licenses.

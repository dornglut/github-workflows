# Dornglut GitHub Workflows

This repository publishes reusable, read-only GitHub Actions orchestration for Dornglut repositories.

Shared workflows call repository-owned validation commands. They do not copy product-specific validation logic, modify implementation source, publish releases, or receive organization secrets.

## Reusable workflows

- [`reusable-rust-cargo-validate.yml`](.github/workflows/reusable-rust-cargo-validate.yml) installs the maintained Rust toolchains, restores Cargo caches, and runs the caller's fixed `cargo +stable validate` authority with bounded failure diagnostics.
- [`reusable-python-repository-validate.yml`](.github/workflows/reusable-python-repository-validate.yml) checks out the caller and runs `python scripts/validate.py`.

Callers own triggers, concurrency, and repository-specific branch rules. They must pin an accepted immutable commit and must not reference `main`.

Canonical validation:

```text
python scripts/validate.py
```

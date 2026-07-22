# Dornglut GitHub Workflows

This repository publishes reusable, read-only GitHub Actions orchestration for Dornglut repositories.

Shared workflows call repository-owned validation commands. They do not copy product-specific validation logic, modify implementation source, publish releases, or receive organization secrets.

## Reusable workflows

- [`reusable-rust-cargo-validate.yml`](.github/workflows/reusable-rust-cargo-validate.yml) checks out the caller and runs `cargo validate`.
- [`reusable-python-repository-validate.yml`](.github/workflows/reusable-python-repository-validate.yml) checks out the caller and runs `python scripts/validate.py`.

Callers must pin an accepted immutable commit. Do not reference `main`.

Canonical validation:

```text
python scripts/validate.py
```

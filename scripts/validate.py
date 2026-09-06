#!/usr/bin/env python3
"""Canonical read-only validation entrypoint for Dornglut shared workflow policy."""

from __future__ import annotations

import sys

import validate_repository as repository


def validate_review_artifact_contract(text: str, failures: list[str]) -> None:
    path_text = repository.relative(repository.RUST_WORKFLOW)
    validation = repository.require_step(
        path_text, text, "Run repository validation authority", failures
    )
    artifact = repository.require_step(
        path_text, text, "Upload repository review artifacts", failures
    )
    diagnostics = repository.require_step(
        path_text, text, "Upload validation diagnostics", failures
    )
    if None in (validation, artifact, diagnostics):
        return

    expected_environment_line = (
        "          REPOSITORY_REVIEW_ARTIFACT_DIR: "
        "${{ runner.temp }}/repository-review-artifacts"
    )
    environment_lines = [
        line
        for line in validation.splitlines()
        if line.lstrip().startswith("REPOSITORY_REVIEW_ARTIFACT_DIR:")
    ]
    if environment_lines != [expected_environment_line]:
        repository.fail(
            f"{path_text}: canonical Rust validation must receive exactly the fixed review-artifact directory",
            failures,
        )
    if text.count("REPOSITORY_REVIEW_ARTIFACT_DIR") != 1:
        repository.fail(
            f"{path_text}: review-artifact environment authority must appear exactly once",
            failures,
        )

    expected_artifact_lines = [
        "        if: success()",
        (
            "        uses: actions/upload-artifact@"
            "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7"
        ),
        "        with:",
        (
            "          name: rust-repository-review-artifacts-"
            "${{ steps.revision.outputs.expected_revision }}"
        ),
        "          path: ${{ runner.temp }}/repository-review-artifacts",
        "          if-no-files-found: ignore",
        "          retention-days: 7",
    ]
    artifact_lines = [line for line in artifact.splitlines() if line.strip()]
    if artifact_lines != expected_artifact_lines:
        repository.fail(
            f"{path_text}: review artifact step must exactly match the fixed success-only upload contract",
            failures,
        )

    if text.count("${{ runner.temp }}/repository-review-artifacts") != 2:
        repository.fail(
            f"{path_text}: fixed review-artifact path must appear only in validation and upload",
            failures,
        )

    upload_pin = (
        "uses: actions/upload-artifact@"
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7"
    )
    if text.count(upload_pin) != 2:
        repository.fail(
            f"{path_text}: Rust profile must contain exactly review and failure artifact uploads",
            failures,
        )

    step_headers = (
        "      - name: Run repository validation authority\n",
        "      - name: Upload repository review artifacts\n",
        "      - name: Upload validation diagnostics\n",
    )
    step_indexes = tuple(text.index(header) for header in step_headers)
    if not (step_indexes[0] < step_indexes[1] < step_indexes[2]):
        repository.fail(
            f"{path_text}: review artifacts must publish after successful validation and before failure diagnostics",
            failures,
        )


def main() -> int:
    failures: list[str] = []
    rust_text = repository.read_text(repository.RUST_WORKFLOW, failures)
    if rust_text is not None:
        validate_review_artifact_contract(rust_text, failures)

    if failures:
        print("repository validation failed:", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    return repository.main()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only validation for Dornglut shared workflow policy."""

from __future__ import annotations

import sys
from pathlib import Path

from validate_diagnostics import validate_diagnostic_contract
from validate_support import (
    EXPECTED_PYTHON_COMMAND,
    EXPECTED_RUST_COMMAND,
    EXPECTED_WORKFLOW_FILES,
    FORBIDDEN_IN_CHECKOUT_DIAGNOSTICS,
    HARDCODED_RUST_VERSION_DOC_RE,
    PYTHON_REQUIRED_FRAGMENTS,
    PYTHON_WORKFLOW,
    ROOT,
    RUST_REQUIRED_FRAGMENTS,
    RUST_TOOLCHAIN_INSTALL_RE,
    RUST_WORKFLOW,
    SELF_WORKFLOW,
    TEXT_SUFFIXES,
    WORKFLOW_DIR,
    WORKFLOW_INPUT_RE,
    fail,
    read_text,
    relative,
    require_step,
    validate_required_files,
    validate_revision_contract,
    validate_text_file,
    validate_workflow_baseline,
)


def validate_rust_review_artifact_contract(text: str, failures: list[str]) -> None:
    path_text = relative(RUST_WORKFLOW)
    validation = require_step(path_text, text, "Run repository validation authority", failures)
    artifact = require_step(path_text, text, "Upload repository review artifacts", failures)
    diagnostics = require_step(path_text, text, "Upload validation diagnostics", failures)
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
        fail(
            f"{path_text}: canonical Rust validation must receive exactly the fixed review-artifact directory",
            failures,
        )
    if text.count("REPOSITORY_REVIEW_ARTIFACT_DIR") != 1:
        fail(
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
        fail(
            f"{path_text}: review artifact step must exactly match the fixed success-only upload contract",
            failures,
        )

    if text.count("${{ runner.temp }}/repository-review-artifacts") != 2:
        fail(
            f"{path_text}: fixed review-artifact path must appear only in validation and upload",
            failures,
        )
    upload_pin = (
        "uses: actions/upload-artifact@"
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7"
    )
    if text.count(upload_pin) != 2:
        fail(
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
        fail(
            f"{path_text}: review artifacts must publish after successful validation and before failure diagnostics",
            failures,
        )


def validate_workflows(failures: list[str]) -> None:
    workflow_files = {path.name for path in WORKFLOW_DIR.glob("*.yml") if path.is_file()}
    if workflow_files != EXPECTED_WORKFLOW_FILES:
        fail(
            "workflow inventory mismatch; "
            f"expected {sorted(EXPECTED_WORKFLOW_FILES)}, found {sorted(workflow_files)}",
            failures,
        )

    texts: dict[Path, str] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = validate_workflow_baseline(path, failures)
        if text is not None:
            texts[path] = text

    rust_text = texts.get(RUST_WORKFLOW)
    if rust_text is not None:
        path_text = relative(RUST_WORKFLOW)
        for fragment in RUST_REQUIRED_FRAGMENTS:
            if fragment not in rust_text:
                fail(f"{path_text}: missing required contract fragment: {fragment}", failures)
        toolchain_installs = [
            match.group("toolchain") for match in RUST_TOOLCHAIN_INSTALL_RE.finditer(rust_text)
        ]
        if toolchain_installs != ["stable", '"${toolchain}"']:
            fail(
                f"{path_text}: Rust toolchain installs must be stable plus caller-declared versions, found {toolchain_installs}",
                failures,
            )
        for fragment in FORBIDDEN_IN_CHECKOUT_DIAGNOSTICS:
            if fragment in rust_text:
                fail(f"{path_text}: diagnostic path must remain outside checkout: {fragment}", failures)
        if WORKFLOW_INPUT_RE.search(rust_text):
            fail(f"{path_text}: inputs and secrets are forbidden for the fixed Rust profile", failures)
        validate_revision_contract(RUST_WORKFLOW, rust_text, failures)
        validate_diagnostic_contract(
            RUST_WORKFLOW,
            rust_text,
            EXPECTED_RUST_COMMAND,
            "rust-repository-validation.log",
            "rust-repository-validation-diagnostics",
            failures,
        )
        validate_rust_review_artifact_contract(rust_text, failures)

    python_text = texts.get(PYTHON_WORKFLOW)
    if python_text is not None:
        path_text = relative(PYTHON_WORKFLOW)
        for fragment in PYTHON_REQUIRED_FRAGMENTS:
            if fragment not in python_text:
                fail(f"{path_text}: missing required contract fragment: {fragment}", failures)
        if WORKFLOW_INPUT_RE.search(python_text):
            fail(f"{path_text}: inputs and secrets are forbidden for the fixed Python profile", failures)
        if "REPOSITORY_REVIEW_ARTIFACT_DIR" in python_text:
            fail(f"{path_text}: review-artifact publication belongs only to the Rust profile", failures)
        validate_revision_contract(PYTHON_WORKFLOW, python_text, failures)
        validate_diagnostic_contract(
            PYTHON_WORKFLOW,
            python_text,
            EXPECTED_PYTHON_COMMAND,
            "python-repository-validation.log",
            "python-repository-validation-diagnostics",
            failures,
        )

    self_text = texts.get(SELF_WORKFLOW)
    if self_text is not None:
        expected_local_call = "uses: ./.github/workflows/reusable-python-repository-validate.yml"
        if self_text.count(expected_local_call) != 1:
            fail(
                f"{relative(SELF_WORKFLOW)}: self-validation must call the local reusable Python workflow exactly once",
                failures,
            )


def validate_dependabot(failures: list[str]) -> None:
    path = ROOT / ".github" / "dependabot.yml"
    text = read_text(path, failures)
    if text is None:
        return
    for fragment in (
        "version: 2",
        "package-ecosystem: github-actions",
        "directory: /",
        "interval: weekly",
        "open-pull-requests-limit: 5",
    ):
        if fragment not in text:
            fail(f"{relative(path)}: missing required fragment {fragment!r}", failures)


def validate_documented_contract(failures: list[str]) -> None:
    checks = {
        "LICENSE": (
            "Apache License",
            "Version 2.0, January 2004",
            "END OF TERMS AND CONDITIONS",
        ),
        "README.md": (
            "full commit SHAs",
            "Dependabot proposes reviewed updates",
            "normative [reusable workflow contract]",
            "## License",
            "[Apache License 2.0](LICENSE)",
            "`Apache-2.0`",
            "does not use the separate commercial licensing path",
        ),
        "AGENTS.md": (
            "Pin every external Action to a full commit SHA",
            "persist-credentials: false",
        ),
        "docs/contract.md": (
            "## Dependency and checkout contract",
            "## Python documentation profile",
            "pull-request callers validate `github.event.pull_request.head.sha`",
            "compact success evidence",
            "caller-declared `rust-version` values",
            "temporary archive under `RUNNER_TEMP`",
            "rust-repository-validation-diagnostics",
            "python-repository-validation-diagnostics",
            "REPOSITORY_REVIEW_ARTIFACT_DIR",
            "rust-repository-review-artifacts-<exact-revision>",
        ),
        "docs/security.md": (
            "full commit SHA",
            "persist-credentials: false",
            "resolve the caller revision from the triggering event",
            "REPOSITORY_REVIEW_ARTIFACT_DIR",
            "seven days",
        ),
        "docs/versioning.md": (
            "External Action updates are proposed by Dependabot",
            "Action dependencies",
        ),
    }
    for path_text, fragments in checks.items():
        text = read_text(ROOT / path_text, failures)
        if text is None:
            continue
        for fragment in fragments:
            if fragment not in text:
                fail(f"{path_text}: missing required contract fragment {fragment!r}", failures)
        if path_text == "docs/contract.md" and HARDCODED_RUST_VERSION_DOC_RE.search(text):
            fail(f"{path_text}: hardcoded caller Rust version is forbidden", failures)


def main() -> int:
    failures: list[str] = []

    validate_required_files(failures)

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == "LICENSE":
            validate_text_file(path, failures)

    validate_workflows(failures)
    validate_dependabot(failures)
    validate_documented_contract(failures)

    if failures:
        print("repository validation failed:", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

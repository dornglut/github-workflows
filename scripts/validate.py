#!/usr/bin/env python3
"""Read-only validation for Dornglut shared workflow policy."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".txt", ".py"}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
WRITE_PERMISSION_RE = re.compile(r"^\s+[a-zA-Z0-9_-]+:\s*write\s*$", re.MULTILINE)
WORKFLOW_INPUT_RE = re.compile(r"^\s{4}(inputs|secrets):\s*$", re.MULTILINE)
VALIDATE_COMMAND_RE = re.compile(r"^cargo(?:\s+\+[^\s]+)?\s+validate(?:\s|$)")
PYTHON_VALIDATE_COMMAND_RE = re.compile(r"^python\s+scripts/validate\.py(?:\s|$)")
USES_LINE_RE = re.compile(r"^\s*uses:\s*(?P<reference>\S+?)(?:\s+#\s*(?P<comment>\S+))?\s*$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUST_TOOLCHAIN_INSTALL_RE = re.compile(
    r"rustup toolchain install (?P<toolchain>\S+) --profile minimal --component rustfmt,clippy"
)
HARDCODED_RUST_VERSION_DOC_RE = re.compile(r"\bRust \d+\.\d+(?:\.\d+)?\b")

WORKFLOW_DIR = ROOT / ".github" / "workflows"
RUST_WORKFLOW = WORKFLOW_DIR / "reusable-rust-cargo-validate.yml"
PYTHON_WORKFLOW = WORKFLOW_DIR / "reusable-python-repository-validate.yml"
SELF_WORKFLOW = WORKFLOW_DIR / "validate.yml"
EXPECTED_WORKFLOW_FILES = {
    "reusable-python-repository-validate.yml",
    "reusable-rust-cargo-validate.yml",
    "validate.yml",
}

ACTION_PINS = {
    "actions/checkout": (
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "v7.0.1",
    ),
    "Swatinem/rust-cache": (
        "e18b497796c12c097a38f9edb9d0641fb99eee32",
        "v2",
    ),
    "actions/upload-artifact": (
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "v7",
    ),
}

EXPECTED_RUST_COMMAND = "cargo +stable validate"
EXPECTED_PYTHON_COMMAND = "python scripts/validate.py"
DIAGNOSTIC_LINE_LIMIT = 40
DIAGNOSTIC_TAIL_LIMIT = 160

RUST_REQUIRED_FRAGMENTS = (
    "clean: true",
    "fetch-depth: 1",
    "persist-credentials: false",
    "rustup toolchain install stable --profile minimal --component rustfmt,clippy",
    'metadata_root="${RUNNER_TEMP}/caller-cargo-metadata"',
    'git archive --format=tar HEAD | tar -xf - -C "${metadata_root}"',
    "cargo +stable metadata \\",
    '--manifest-path "${metadata_root}/Cargo.toml" \\',
    "--no-deps \\",
    "--format-version 1 |",
    'package.get("rust_version")',
    '[[ -n "${toolchain}" ]] || continue',
    'rustup toolchain install "${toolchain}" --profile minimal --component rustfmt,clippy',
)
PYTHON_REQUIRED_FRAGMENTS = (
    "clean: true",
    "fetch-depth: 1",
    "persist-credentials: false",
)
FORBIDDEN_IN_CHECKOUT_DIAGNOSTICS = (
    "tee validation.log",
    "path: validation.log",
    "run: rm -f validation.log",
)
EXPECTED_REVISION_OUTPUT = "expected_revision=${expected_revision}"
EXPECTED_REVISION_REF = "ref: ${{ steps.revision.outputs.expected_revision }}"


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path, failures: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        fail(f"{relative(path)}: failed to read UTF-8 text: {error}", failures)
        return None


def validate_text_file(path: Path, failures: list[str]) -> None:
    data = path.read_bytes()
    path_text = relative(path)

    if b"\x00" in data:
        fail(f"{path_text}: contains a NUL byte", failures)
        return

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"{path_text}: is not valid UTF-8", failures)
        return

    if text and not text.endswith("\n"):
        fail(f"{path_text}: must end with a newline", failures)

    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            fail(f"{path_text}:{line_number}: trailing whitespace", failures)
        if "\t" in line:
            fail(f"{path_text}:{line_number}: tab character", failures)

    if path.suffix.lower() != ".md":
        return

    for match in LINK_RE.finditer(text):
        raw_target = match.group(1).strip()
        target = raw_target.split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            fail(f"{path_text}: link escapes repository: {raw_target}", failures)
            continue
        if not resolved.exists():
            fail(f"{path_text}: broken relative link: {raw_target}", failures)


def validate_required_files(failures: list[str]) -> None:
    manifest = ROOT / "validation-required-files.txt"
    if not manifest.is_file():
        fail("validation-required-files.txt: missing", failures)
        return

    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        required = raw_line.strip()
        if not required or required.startswith("#"):
            continue
        path = ROOT / required
        if not path.is_file():
            fail(f"{required}: required file is missing", failures)
        elif path.stat().st_size == 0:
            fail(f"{required}: required file is empty", failures)


def validate_action_reference(path_text: str, line: str, failures: list[str]) -> None:
    match = USES_LINE_RE.match(line)
    if match is None:
        fail(f"{path_text}: malformed uses line: {line.strip()}", failures)
        return

    reference = match.group("reference")
    comment = match.group("comment")

    starts_quoted = reference[:1] in {'"', "'"}
    ends_quoted = reference[-1:] in {'"', "'"}
    if starts_quoted or ends_quoted:
        if not starts_quoted or not ends_quoted or reference[0] != reference[-1]:
            fail(f"{path_text}: mismatched quotes in uses reference {reference!r}", failures)
            return
        reference = reference[1:-1]
        if not reference:
            fail(f"{path_text}: quoted uses reference must not be empty", failures)
            return
        if reference.startswith("./"):
            fail(f"{path_text}: local reusable workflow reference must remain unquoted", failures)
            return

    if reference.startswith("./"):
        if reference != "./.github/workflows/reusable-python-repository-validate.yml":
            fail(f"{path_text}: unexpected local workflow reference {reference!r}", failures)
        if path_text != ".github/workflows/validate.yml":
            fail(f"{path_text}: local reusable workflow is permitted only in validate.yml", failures)
        if comment is not None:
            fail(f"{path_text}: local reusable workflow must not have a version comment", failures)
        return

    if "@" not in reference:
        fail(f"{path_text}: external Action reference lacks a commit: {reference!r}", failures)
        return

    action, revision = reference.rsplit("@", 1)
    if not FULL_SHA_RE.fullmatch(revision):
        fail(f"{path_text}: {action} must use a full 40-character commit SHA", failures)
        return

    expected = ACTION_PINS.get(action)
    if expected is None:
        fail(f"{path_text}: unreviewed external Action {action!r}", failures)
        return

    expected_revision, expected_comment = expected
    if revision != expected_revision:
        fail(
            f"{path_text}: {action} must use reviewed revision {expected_revision}, found {revision}",
            failures,
        )
    if comment != expected_comment:
        fail(
            f"{path_text}: {action} must document release {expected_comment!r} on the same line",
            failures,
        )


def validate_workflow_baseline(path: Path, failures: list[str]) -> str | None:
    text = read_text(path, failures)
    if text is None:
        return None
    path_text = relative(path)

    if path.name.startswith("reusable-") and "workflow_call:" not in text:
        fail(f"{path_text}: reusable workflow must declare workflow_call", failures)
    if "pull_request_target:" in text:
        fail(f"{path_text}: pull_request_target is forbidden", failures)
    if "permissions: write-all" in text:
        fail(f"{path_text}: write-all permission is forbidden", failures)
    if WRITE_PERMISSION_RE.search(text):
        fail(f"{path_text}: write permission is forbidden", failures)
    if "contents: read" not in text:
        fail(f"{path_text}: must declare contents: read", failures)
    if "continue-on-error:" in text:
        fail(f"{path_text}: continue-on-error is forbidden", failures)
    if "secrets: inherit" in text:
        fail(f"{path_text}: inherited secrets are forbidden", failures)
    if "persist-credentials: true" in text:
        fail(f"{path_text}: persisted checkout credentials are forbidden", failures)

    for line in text.splitlines():
        if line.lstrip().startswith("uses:"):
            validate_action_reference(path_text, line, failures)

    checkout_count = sum(
        text.count(fragment)
        for fragment in (
            "uses: actions/checkout@",
            'uses: "actions/checkout@',
            "uses: 'actions/checkout@",
        )
    )
    persist_false_count = text.count("persist-credentials: false")
    if path.name.startswith("reusable-") and checkout_count != 1:
        fail(f"{path_text}: reusable profile must have exactly one checkout", failures)
    if checkout_count != persist_false_count:
        fail(
            f"{path_text}: every checkout requires exactly one persist-credentials: false entry",
            failures,
        )

    return text


def step_body(text: str, name: str) -> str | None:
    pattern = re.compile(
        rf"^      - name: {re.escape(name)}\n(?P<body>.*?)(?=^      - name:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return None if match is None else match.group("body")


def require_step(
    path_text: str, text: str, name: str, failures: list[str]
) -> str | None:
    body = step_body(text, name)
    if body is None:
        fail(f"{path_text}: missing required step {name!r}", failures)
    return body


def validate_revision_contract(path: Path, text: str, failures: list[str]) -> None:
    path_text = relative(path)
    resolution = require_step(path_text, text, "Resolve expected caller revision", failures)
    checkout = require_step(path_text, text, "Check out caller repository", failures)
    proof = require_step(path_text, text, "Prove checked-out caller revision", failures)
    validation = require_step(path_text, text, "Run repository validation authority", failures)
    if None in (resolution, checkout, proof, validation):
        return

    for fragment in (
        "EVENT_NAME: ${{ github.event_name }}",
        "EVENT_SHA: ${{ github.sha }}",
        "PULL_REQUEST_HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
        "PULL_REQUEST_BASE_SHA: ${{ github.event.pull_request.base.sha }}",
        'pull_request) expected_revision="${PULL_REQUEST_HEAD_SHA}"',
        'push|workflow_dispatch) expected_revision="${EVENT_SHA}"',
        'if [[ -z "${expected_revision}" ]]',
        "Unsupported caller event:",
        EXPECTED_REVISION_OUTPUT,
        "pull_request_base_revision=${PULL_REQUEST_BASE_SHA}",
    ):
        if fragment not in resolution:
            fail(f"{path_text}: expected-revision resolution missing {fragment!r}", failures)

    if EXPECTED_REVISION_REF not in checkout:
        fail(f"{path_text}: checkout must explicitly use the resolved expected revision", failures)

    for fragment in (
        "EXPECTED_REVISION: ${{ steps.revision.outputs.expected_revision }}",
        "PULL_REQUEST_BASE_REVISION: ${{ steps.revision.outputs.pull_request_base_revision }}",
    ):
        if fragment not in validation:
            fail(f"{path_text}: validation step must receive revision output {fragment!r}", failures)

    for fragment in (
        'actual_revision="$(git rev-parse HEAD)"',
        '[[ "${actual_revision}" != "${EXPECTED_REVISION}" ]]',
        "Expected revision:",
        "Actual checked-out revision:",
        "Conclusion:",
    ):
        if fragment not in proof:
            fail(f"{path_text}: checkout identity proof missing {fragment!r}", failures)

    if not (text.index(proof) < text.index(validation)):
        fail(f"{path_text}: repository validation must follow revision equality proof", failures)


def validate_diagnostic_contract(
    path: Path,
    text: str,
    command: str,
    log_filename: str,
    artifact_name: str,
    failures: list[str],
) -> None:
    path_text = relative(path)
    validation = require_step(path_text, text, "Run repository validation authority", failures)
    artifact = require_step(path_text, text, "Upload validation diagnostics", failures)
    cleanup = require_step(path_text, text, "Remove validation diagnostics", failures)
    if None in (validation, artifact, cleanup):
        return

    command_lines = [
        line.strip()
        for line in validation.splitlines()
        if line.strip().startswith(command)
    ]
    expected_command_line = f'{command} >"${{log_path}}" 2>&1'
    if command_lines != [expected_command_line]:
        fail(
            f"{path_text}: expected exactly one fixed captured validation command, found {command_lines}",
            failures,
        )
    if command == EXPECTED_RUST_COMMAND:
        rust_validation_lines = [
            line.strip()
            for line in text.splitlines()
            if VALIDATE_COMMAND_RE.match(line.strip())
        ]
        if rust_validation_lines != [expected_command_line]:
            fail(
                f"{path_text}: expected exactly one Rust validation command, found {rust_validation_lines}",
                failures,
            )
    if command == EXPECTED_PYTHON_COMMAND:
        python_validation_lines = [
            line.strip()
            for line in text.splitlines()
            if PYTHON_VALIDATE_COMMAND_RE.match(line.strip())
        ]
        if python_validation_lines != [expected_command_line]:
            fail(
                f"{path_text}: expected exactly one Python validation command, found {python_validation_lines}",
                failures,
            )
    success_marker = 'echo "Conclusion: PASS"'
    failure_marker = 'echo "Conclusion: FAIL"'
    status_marker = "validation_status=$?"
    success_branch_marker = 'if [[ "${validation_status}" -eq 0 ]]'
    final_exit_marker = 'exit "${validation_status}"'
    tail_marker = f"tail -n {DIAGNOSTIC_TAIL_LIMIT}"
    status_index = validation.find(status_marker)
    success_branch_index = validation.find(success_branch_marker)
    success_index = validation.find(success_marker)
    failure_index = validation.find(failure_marker)
    final_exit_index = validation.rfind(final_exit_marker)
    tail_index = validation.find(tail_marker)
    if min(
        status_index,
        success_branch_index,
        success_index,
        failure_index,
        final_exit_index,
        tail_index,
    ) < 0:
        fail(f"{path_text}: validation result record is incomplete", failures)
        return
    success_result = validation[success_branch_index:failure_index]
    failure_result = validation[success_index + len(success_marker) :]
    for fragment in (
        f'log_path="${{RUNNER_TEMP}}/{log_filename}"',
        status_marker,
        success_branch_marker,
        success_marker,
        f"head -n {DIAGNOSTIC_LINE_LIMIT}",
        tail_marker,
        f"Complete diagnostics: {artifact_name} artifact (3-day retention)",
        final_exit_marker,
    ):
        if fragment not in validation:
            fail(f"{path_text}: diagnostics contract missing {fragment!r}", failures)
    common_result_fields = (
        'echo "Repository: ${GITHUB_REPOSITORY}"',
        'echo "Event: ${GITHUB_EVENT_NAME}"',
        'echo "Expected revision: ${EXPECTED_REVISION}"',
        'echo "Actual checked-out revision: $(git rev-parse HEAD)"',
        'if [[ -n "${PULL_REQUEST_BASE_REVISION}" ]]',
        'echo "Pull-request base revision: ${PULL_REQUEST_BASE_REVISION}"',
        f'echo "Canonical command: {command}"',
    )
    result_records = (
        ("success", success_result, (*common_result_fields, success_marker)),
        (
            "failure",
            failure_result,
            (
                *common_result_fields,
                'echo "Validation exit status: ${validation_status}"',
                failure_marker,
            ),
        ),
    )
    for result_name, result_text, fields in result_records:
        previous_index = -1
        for fragment in fields:
            field_index = result_text.find(fragment)
            if field_index < 0:
                fail(f"{path_text}: {result_name} result missing {fragment!r}", failures)
            elif field_index < previous_index:
                fail(f"{path_text}: {result_name} result fields are out of order", failures)
            previous_index = field_index
    for fragment in (
        'echo "Validation exit status: ${validation_status}"',
        final_exit_marker,
    ):
        if fragment not in validation:
            fail(f"{path_text}: diagnostics contract missing {fragment!r}", failures)
    if not (
        status_index < success_branch_index < success_index < failure_index < final_exit_index
    ):
        fail(f"{path_text}: validation result ordering must preserve the original status", failures)
    if "tee" in validation or "cat " in validation:
        fail(f"{path_text}: complete validation output must not stream to the console", failures)
    if success_branch_index > tail_index:
        fail(f"{path_text}: successful validation must not print complete diagnostics", failures)

    for fragment in (
        "if: failure()",
        f"name: {artifact_name}",
        f"path: ${{{{ runner.temp }}}}/{log_filename}",
        "if-no-files-found: error",
        "retention-days: 3",
    ):
        if fragment not in artifact:
            fail(f"{path_text}: failure artifact contract missing {fragment!r}", failures)
    if "if: always()" not in cleanup or f'rm -f "${{RUNNER_TEMP}}/{log_filename}"' not in cleanup:
        fail(f"{path_text}: diagnostics must be cleaned unconditionally", failures)


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

    python_text = texts.get(PYTHON_WORKFLOW)
    if python_text is not None:
        path_text = relative(PYTHON_WORKFLOW)
        for fragment in PYTHON_REQUIRED_FRAGMENTS:
            if fragment not in python_text:
                fail(f"{path_text}: missing required contract fragment: {fragment}", failures)
        if WORKFLOW_INPUT_RE.search(python_text):
            fail(f"{path_text}: inputs and secrets are forbidden for the fixed Python profile", failures)
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
        ),
        "docs/security.md": (
            "full commit SHA",
            "persist-credentials: false",
            "resolve the caller revision from the triggering event",
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

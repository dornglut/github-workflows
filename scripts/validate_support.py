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


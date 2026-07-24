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
USES_LINE_RE = re.compile(r"^\s*uses:\s*(?P<reference>\S+?)(?:\s+#\s*(?P<comment>\S+))?\s*$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

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
        "d23441a48e516b6c34aea4fa41551a30e30af803",
        "v6",
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

EXPECTED_RUST_COMMAND = 'cargo +stable validate 2>&1 | tee "${RUNNER_TEMP}/validation.log"'
EXPECTED_PYTHON_COMMAND = "python scripts/validate.py"
RUST_REQUIRED_FRAGMENTS = (
    "clean: true",
    "fetch-depth: 1",
    "persist-credentials: false",
    "rustup toolchain install stable --profile minimal --component rustfmt,clippy",
    "rustup toolchain install 1.93.0 --profile minimal --component rustfmt,clippy",
    "set -o pipefail",
    EXPECTED_RUST_COMMAND,
    "if: failure()",
    "path: ${{ runner.temp }}/validation.log",
    "retention-days: 3",
    "if: always()",
    'run: rm -f "${RUNNER_TEMP}/validation.log"',
)
PYTHON_REQUIRED_FRAGMENTS = (
    "clean: true",
    "fetch-depth: 1",
    "persist-credentials: false",
    EXPECTED_PYTHON_COMMAND,
)
FORBIDDEN_IN_CHECKOUT_DIAGNOSTICS = (
    "tee validation.log",
    "path: validation.log",
    "run: rm -f validation.log",
)


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

    checkout_count = text.count("uses: actions/checkout@")
    persist_false_count = text.count("persist-credentials: false")
    if checkout_count != persist_false_count:
        fail(
            f"{path_text}: every checkout requires exactly one persist-credentials: false entry",
            failures,
        )

    return text


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
        for fragment in FORBIDDEN_IN_CHECKOUT_DIAGNOSTICS:
            if fragment in rust_text:
                fail(f"{path_text}: diagnostic path must remain outside checkout: {fragment}", failures)
        if WORKFLOW_INPUT_RE.search(rust_text):
            fail(f"{path_text}: inputs and secrets are forbidden for the fixed Rust profile", failures)
        validate_commands = [
            line.strip()
            for line in rust_text.splitlines()
            if VALIDATE_COMMAND_RE.match(line.strip())
        ]
        if validate_commands != [EXPECTED_RUST_COMMAND]:
            fail(
                f"{path_text}: expected exactly one fixed validation command, found {validate_commands}",
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
        python_commands = [
            line.strip().removeprefix("run: ").strip()
            for line in python_text.splitlines()
            if line.strip().startswith("run: python ")
        ]
        if python_commands != [EXPECTED_PYTHON_COMMAND]:
            fail(
                f"{path_text}: expected exactly one fixed validation command, found {python_commands}",
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
        "README.md": (
            "full commit SHAs",
            "Dependabot proposes reviewed updates",
        ),
        "AGENTS.md": (
            "Pin every external Action to a full commit SHA",
            "persist-credentials: false",
        ),
        "docs/contract.md": (
            "## Dependency and checkout contract",
            "## Python documentation profile",
        ),
        "docs/security.md": (
            "full commit SHA",
            "persist-credentials: false",
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


def main() -> int:
    failures: list[str] = []

    validate_required_files(failures)

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
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

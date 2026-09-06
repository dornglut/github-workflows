"""Validation-result and failure-diagnostic contract checks."""

from __future__ import annotations

from pathlib import Path

from validate_support import (
    DIAGNOSTIC_LINE_LIMIT,
    DIAGNOSTIC_TAIL_LIMIT,
    EXPECTED_PYTHON_COMMAND,
    EXPECTED_RUST_COMMAND,
    PYTHON_VALIDATE_COMMAND_RE,
    VALIDATE_COMMAND_RE,
    fail,
    relative,
    require_step,
)


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


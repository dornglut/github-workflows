"""Exercise the actual embedded classifier, without network or credentials."""
import textwrap


def validate_change_aware(root, failures):
    workflow = (root / ".github/workflows/reusable-rust-change-aware.yml").read_text(encoding="utf-8")
    try:
        source = workflow.split("          python -I - <<'PY'\n", 1)[1].split("\n          PY\n", 1)[0]
        ns = {"__name__": "classifier_test"}
        exec(compile(textwrap.dedent(source), "<workflow classifier>", "exec"), ns)
        regular = ("100644", "blob", "a" * 40)
        changed = ("100644", "blob", "b" * 40)
        symlink = ("120000", "blob", "b" * 40)
        old = {"README.md": regular, "src/main.rs": regular}
        new = {**old, "README.md": changed}
        allowed = ns["allowlist"](b"README.md\n")
        diff = ns["eligible_difference"]
        assert diff(old, new, allowed)
        assert not diff(old, old, allowed)
        assert not diff(old, {**new, "src/main.rs": changed}, allowed)
        assert not diff(old, {"src/main.rs": regular}, allowed)
        assert not diff(old, {**new, "extra.md": changed}, allowed)
        assert not diff(old, {**old, "README.md": symlink}, allowed)
        assert not diff(old, {**old, "README.md": ("100755", "blob", "a" * 40)}, allowed)
        for raw in (b"README.md", b"*.md\n", b"../README.md\n", b"README.md\nREADME.md\n", b"src/main.rs\n", b"README.md\r\n", b"docs/.md\n", b"README.md\xc2\x85STATUS.md\n"):
            try:
                ns["allowlist"](raw)
            except ValueError:
                pass
            else:
                raise AssertionError("unsafe allowlist accepted")
        accepted = {**old, ns["ALLOWLIST"]: regular, ns["CALLER"]: regular}
        assert ns["trusted_policy"](accepted, accepted, allowed)
        assert not ns["trusted_policy"](accepted, {**accepted, ns["ALLOWLIST"]: changed}, allowed)
        assert not ns["trusted_policy"](accepted, {**accepted, ns["CALLER"]: changed}, allowed)
        assert not ns["trusted_policy"](accepted, {**accepted, ns["PARTITIONS"]: regular}, allowed)
        prefix = "Validate application / "
        full = [
            {"name": prefix + "Full validation / Validation / complete", "conclusion": "success", "steps": [
                {"name": "Prove validation caller revision", "conclusion": "success"},
                {"name": "Run repository validation authority", "conclusion": "success"},
            ]},
            {"name": prefix + "Full validation / Repository baseline", "conclusion": "success"},
            {"name": prefix + "Repository baseline", "conclusion": "success"},
        ]
        job_run = {"head_sha": "d" * 40, "id": 1, "run_attempt": 1}
        full = [{**job, "head_sha": job_run["head_sha"], "run_id": 1, "run_attempt": 1} for job in full]
        assert ns["full_jobs"](full, job_run)
        assert not ns["full_jobs"](full[1:], job_run)
        assert not ns["full_jobs"]([{**full[0], "conclusion": "skipped"}, *full[1:]], job_run)
        assert not ns["full_jobs"]([{**full[0], "steps": []}, *full[1:]], job_run)
        assert not ns["full_jobs"]([*full, full[0]], job_run)
        assert not ns["full_jobs"]([{**full[0], "head_sha": "f" * 40}, *full[1:]], job_run)
        assert not ns["full_jobs"](full, {**job_run, "run_attempt": 2})
        pin = "c" * 40
        repo = "example/repo"
        run = {
            "id": 1, "run_attempt": 1, "status": "completed", "conclusion": "success",
            "path": ns["CALLER"], "repository": {"full_name": repo},
            "head_repository": {"full_name": repo}, "head_sha": "d" * 40,
            "event": "push", "head_branch": "main",
            "referenced_workflows": [
                {"path": ns[key] + "@" + pin, "sha": pin} for key in ("WRAPPER", "FULL")
            ],
        }
        args = (repo, pin, "main", "feature", 42, "e" * 40)
        assert ns["run_matches"](run, *args)
        assert not ns["run_matches"]({**run, "referenced_workflows": []}, *args)
        assert not ns["run_matches"]({**run, "head_branch": "other"}, *args)
        assert not ns["run_matches"]({**run, "head_repository": {"full_name": "other/repo"}}, *args)
        assert not ns["run_matches"]({**run, "event": "pull_request"}, *args)
        # Drive the actual planner against synthetic, exact revision-bound API data.
        accepted_sha = "e" * 40
        current_sha = "f" * 40
        base_tree_sha = "1" * 40
        accepted = {
            **old, ns["ALLOWLIST"]: regular, ns["CALLER"]: regular,
        }
        current = {**accepted, "README.md": changed}
        doc_event = {
            "repository": {"full_name": repo, "default_branch": "main"},
            "number": 42,
            "pull_request": {
                "base": {"sha": accepted_sha, "ref": "main"},
                "head": {"ref": "feature", "repo": {"full_name": repo}},
            },
        }
        run = {**run, "head_sha": accepted_sha}
        full = [{**job, "head_sha": accepted_sha} for job in full]
        def tree_data(entries):
            return {
                "sha": base_tree_sha, "truncated": False,
                "tree": [
                    {"path": path, "mode": mode, "type": kind, "sha": oid}
                    for path, (mode, kind, oid) in entries.items()
                ],
            }

        replies = {
            "git/commits/" + accepted_sha: {"sha": accepted_sha, "tree": {"sha": base_tree_sha}},
            "git/trees/" + base_tree_sha + "?recursive=1": tree_data(accepted),
            "actions/workflows/validation.yml/runs?status=success&per_page=20": {"workflow_runs": [run]},
            "actions/runs/1": run,
            "actions/runs/1/attempts/1/jobs?per_page=100": {"jobs": full, "total_count": len(full)},
        }
        documents = {
            ns["ALLOWLIST"]: b"README.md\n",
            ns["CALLER"]: ("    uses: " + ns["WRAPPER"] + "@" + pin + "\n").encode(),
        }
        choose = ns["choose"]
        def select(tree, event_name="pull_request", api=None):
            return choose(event_name, doc_event, current_sha, api or replies.__getitem__, documents.__getitem__, tree)

        assert select(current) == (accepted_sha, 1)
        assert select({**current, "src/main.rs": changed}) is None
        assert select(current, "workflow_dispatch") is None
        assert select(current, "merge_group") is None
        replies["actions/runs/1/attempts/1/jobs?per_page=100"] = {"jobs": full[1:], "total_count": len(full) - 1}
        assert select(current) is None
        replies["actions/runs/1/attempts/1/jobs?per_page=100"] = {"jobs": full, "total_count": len(full) + 1}
        assert select(current) is None
        for required in (
            "needs: [plan, full, docs]", "if: always()", "name: Repository baseline",
            '[[ "$PLAN" == success ]]', '[[ "$FULL" == success && "$DOCS" == skipped ]]',
            '[[ "$DOCS" == success && "$FULL" == skipped ]]',
            "cargo +stable validate --docs", "uses: ./.github/workflows/reusable-rust-cargo-validate.yml",
            "actions: read", "persist-credentials: false", "python -I -",
            '["git", "show", "HEAD:" + path]',
        ):
            assert required in workflow, f"missing {required}"
    except (AssertionError, IndexError, KeyError, SyntaxError, ValueError) as error:
        failures.append(f"change-aware validation contract: {error}")

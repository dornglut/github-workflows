"""Exercise the actual embedded classifier, without network or credentials."""
import textwrap


def validate_change_aware(root, failures):
    workflow = (root / ".github/workflows/reusable-rust-change-aware.yml").read_text(encoding="utf-8")
    try:
        source = workflow.split("          python - <<'PY'\n", 1)[1].split("\n          PY\n", 1)[0]
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
        for raw in (b"README.md", b"*.md\n", b"../README.md\n", b"README.md\nREADME.md\n", b"src/main.rs\n"):
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
        assert ns["full_jobs"](full)
        assert not ns["full_jobs"](full[1:])
        assert not ns["full_jobs"]([{**full[0], "conclusion": "skipped"}, *full[1:]])
        assert not ns["full_jobs"]([{**full[0], "steps": []}, *full[1:]])
        assert not ns["full_jobs"]([*full, full[0]])
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
        for required in (
            "needs: [plan, full, docs]", "if: always()", "name: Repository baseline",
            '[[ "$PLAN" == success ]]', '[[ "$FULL" == success && "$DOCS" == skipped ]]',
            '[[ "$DOCS" == success && "$FULL" == skipped ]]',
            "cargo +stable validate --docs", "uses: ./.github/workflows/reusable-rust-cargo-validate.yml",
            "actions: read", "persist-credentials: false",
        ):
            assert required in workflow, f"missing {required}"
    except (AssertionError, IndexError, KeyError, SyntaxError, ValueError) as error:
        failures.append(f"change-aware validation contract: {error}")

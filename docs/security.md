# Security model

Shared workflows run in the caller repository's context and therefore use the caller's `GITHUB_TOKEN` and runner environment.

Current workflows:

- declare only `contents: read`;
- do not accept or inherit secrets;
- do not run on `pull_request_target`;
- do not perform deployment or release operations;
- do not accept arbitrary command, script, toolchain, runner, or path inputs;
- resolve the caller revision from the triggering event in the planning job, prove that checkout, and require every validation runner to independently check out and prove the same selected SHA;
- treat `validation-partitions.txt` as untrusted bounded data: regular UTF-8 file only, at most four narrow identifiers, no shell/script/path/runner/toolchain interpretation, and runner-side identifier revalidation;
- use clean shallow checkout with `persist-credentials: false`;
- keep diagnostic files below `RUNNER_TEMP`, outside the caller checkout;
- print only bounded diagnostics and upload the complete short-retention validation log only after failure;
- pin every external Action to a full commit SHA with an inline release comment;
- keep Rust `merge_group` validation independent of optional compiler-cache binary acquisition: skip the sccache Action and wrapper for merge groups while preserving full exact-revision canonical validation;
- permit `continue-on-error` only for pinned optional Rust compiler-cache setup, with the Action's unsafe-on-failure post hook disabled; if setup fails, select direct `rustc` and still require the exact same canonical validation command and aggregate result. Cache setup success alone may enable the source-addressed wrapper; all other workflow steps remain fail-closed;
- receive Action dependency updates through reviewed Dependabot pull requests.

A full commit SHA is the immutable dependency boundary. Release tags in comments are documentation and update metadata, not executable references.

Callers pin the reusable workflow to an immutable commit and retain repository-local branch protection and required checks. The caller controls event triggers and must not use the shared workflow from a privileged `pull_request_target` path. Partition inventory remains repository-owned; caller YAML does not supply semantic lanes or arbitrary execution policy.

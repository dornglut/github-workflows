# Security model

Shared workflows run in the caller repository's context and therefore use the caller's `GITHUB_TOKEN` and runner environment.

Current workflows:

- declare only `contents: read`;
- do not accept or inherit secrets;
- do not run on `pull_request_target`;
- do not perform deployment or release operations;
- do not accept arbitrary command, script, toolchain, runner, or path inputs;
- resolve the caller revision from the triggering event, select it explicitly, and prove the checked-out SHA before validation;
- use clean shallow checkout with `persist-credentials: false`;
- keep diagnostic and review-artifact files below `RUNNER_TEMP`, outside the caller checkout;
- print only bounded diagnostics and upload the complete short-retention validation log only after failure;
- expose one fixed `REPOSITORY_REVIEW_ARTIFACT_DIR` below `RUNNER_TEMP` to Rust canonical validation and upload that directory only after successful validation when the caller populated it;
- never generate caller-specific review evidence in the shared workflow and never treat review-artifact publication as a second validation result;
- pin every external Action to a full commit SHA with an inline release comment;
- receive Action dependency updates through reviewed Dependabot pull requests.

The optional Rust review-artifact boundary uses a workflow-owned path and accepts no caller-supplied path or command. Its upload is read-only with respect to repository contents, uses the already reviewed `actions/upload-artifact` Action, ignores an absent artifact directory, and retains populated review evidence for seven days.

A full commit SHA is the immutable dependency boundary. Release tags in comments are documentation and update metadata, not executable references.

Callers pin the reusable workflow to an immutable commit and retain repository-local branch protection and required checks. The caller controls event triggers and must not use the shared workflow from a privileged `pull_request_target` path.

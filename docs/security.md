# Security model

Shared workflows run in the caller repository's context and therefore use the caller's `GITHUB_TOKEN` and runner environment.

Current workflows:

- declare only `contents: read`;
- do not accept or inherit secrets;
- do not run on `pull_request_target`;
- do not perform deployment or release operations;
- do not accept arbitrary command, script, toolchain, runner, or path inputs;
- check out only the caller revision selected by the triggering workflow;
- keep diagnostic files below `RUNNER_TEMP`, outside the caller checkout;
- upload only the bounded validation log and only after failure;
- use maintained action majors that are statically enforced by repository validation.

Callers must pin the reusable workflow to an immutable commit and retain repository-local branch protection and required checks. The caller controls event triggers and must not use the shared workflow from a privileged `pull_request_target` path.

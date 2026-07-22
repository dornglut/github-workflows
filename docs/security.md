# Security model

Shared workflows run in the caller repository's context and therefore use the caller's `GITHUB_TOKEN` and runner environment.

Current workflows:

- declare only `contents: read`;
- do not accept or inherit secrets;
- do not run on `pull_request_target`;
- do not perform deployment or release operations;
- do not accept arbitrary command inputs;
- use a maintained GitHub checkout action by major version inside this repository.

Callers should pin the reusable workflow to an immutable commit and retain repository-local branch protection and required checks.

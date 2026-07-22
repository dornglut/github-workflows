# Reusable workflow contract

A shared workflow may standardize runner selection, checkout, timeout, permissions, and invocation of a repository-owned command.

It must not:

- redefine the caller's validation semantics;
- mutate source, issues, pull requests, branches, tags, releases, or packages;
- use `pull_request_target`;
- request write permissions;
- receive secrets unless a later accepted ADR authorizes a bounded use case;
- accept an arbitrary command or script as input;
- hide validation failures or convert them into generated commits.

Caller repositories remain responsible for their canonical command, toolchain policy, lockfiles, tests, documentation checks, and exact acceptance criteria.

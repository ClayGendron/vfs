# The shell preserves warnings from partial VFS results

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

Incomplete listings, searches and operational stat failures leave inspectable evidence on the line result.

## The problem

The host drops every stat refusal from the warning list. Other successful verbs can carry warnings, such as an incomplete directory listing, but the adapter examines fatal errors only. Search similarly omits nonfatal warnings. Scripts inspecting the evidence can mistake incomplete results for complete ones.

## Proposed changes

Keep nonfatal warnings returned by successful verbs. Distinguish expected negative existence probes from operational failures while preserving the VFS visibility policy.

## Acceptance tests

Return rows with a warning from a listing and search. Check output, deduplication and the warning record. Compare with an ordinary absent-file predicate.

## Builds on

[src/vfs/shell/host.py L408](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L408) · [src/vfs/shell/host.py L455](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L455) · [src/vfs/shell/host.py L486](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L486) · [src/vfs/base.py L863](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/base.py#L863)

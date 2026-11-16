"""A ten-line model of longest-prefix permission resolution, checked by CrossHair.

`resolve` mirrors the boundary test in vfs's PermissionMap._resolve; `resolve_buggy`
drops the "/" boundary, the classic prefix-match bug. Each carries a contract that a rule
on a directory never governs a sibling whose name merely starts with the same letters.
"""


def resolve(rule: str, path: str) -> str:
    """
    pre: rule.startswith("/") and len(rule) > 1 and not rule.endswith("/")
    post: (path == rule or path.startswith(rule + "/")) == (__return__ == "read")
    """
    if path == rule or path.startswith(rule + "/"):
        return "read"
    return "read_write"


def resolve_buggy(rule: str, path: str) -> str:
    """
    pre: rule.startswith("/") and len(rule) > 1 and not rule.endswith("/")
    post: (path == rule or path.startswith(rule + "/")) == (__return__ == "read")
    """
    if path.startswith(rule):
        return "read"
    return "read_write"

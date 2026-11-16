def membership_budget(in_list: int, params: int) -> int:
    """The tighter of two caps, never below one."""
    b = in_list if in_list < params else params
    return 1 if b == 0 else b


def chunk_lengths(n: int, size: int) -> list[int]:
    """Slice n items into chunks no larger than size; return the lengths."""
    out = []
    left = n
    while left > 0:
        take = size if left > size else left
        out.append(take)
        left -= take
    return out


def may_read(grants: list[str], path: str) -> bool:
    """A caller may read a path it holds a grant on, or under one."""
    return any(path == g or path.startswith(g + "/") for g in grants)

import deal

@deal.post(lambda result: result in ("read", "read_write"))
@deal.ensure(lambda rule, path, result: (result == "read") == (path == rule or path.startswith(rule + "/")))
def resolve(rule: str, path: str) -> str:
    if path.startswith(rule):
        return "read"
    return "read_write"

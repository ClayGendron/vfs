"""S4: GrantWorld.closure memoised per world; the memo is dropped whenever member_of is replaced... (member_of is only ever built once)."""
p = "/Users/claygendron/Git/Repos/vfs/tests/support/oracles/grants.py"
s = open(p).read()
old = '''    def closure(self, principal: str) -> frozenset[str]:
        """Every group *principal* reaches, directly or through nesting."""
        seen: set[str] = set()
'''
new = '''    _closures: dict[str, frozenset[str]] = field(default_factory=dict, repr=False, compare=False)

    def closure(self, principal: str) -> frozenset[str]:
        """Every group *principal* reaches, directly or through nesting."""
        if principal in self._closures:
            return self._closures[principal]
        self._closures[principal] = found = self._walk(principal)
        return found

    def _walk(self, principal: str) -> frozenset[str]:
        seen: set[str] = set()
'''
assert s.count(old) == 1
open(p, "w").write(s.replace(old, new))

"""A toy governed store, a reference model, and a stateful machine that compares them."""

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

names = st.sampled_from(["a", "ab", "b"])
paths = st.lists(names, min_size=1, max_size=3).map(lambda parts: "/" + "/".join(parts))


class ToyStore:
    """The system under test, with a planted bug: a grant on /a also opens /ab."""

    def __init__(self):
        self.files: dict[str, str] = {}
        self.grants: set[str] = set()

    def read(self, path):
        if not any(path.startswith(g) for g in self.grants):
            return "denied"
        return self.files.get(path, "missing")


def model_read(files, grants, path):
    parts = path.strip("/").split("/")
    ancestors = {"/" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)}
    if not ancestors & grants:
        return "denied"
    return files.get(path, "missing")


class GovernedStore(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.sut = ToyStore()
        self.files: dict[str, str] = {}
        self.grants: set[str] = set()

    @rule(path=paths, body=st.text(max_size=3))
    def write(self, path, body):
        self.sut.files[path] = body
        self.files[path] = body

    @rule(path=paths)
    def grant(self, path):
        self.sut.grants.add(path)
        self.grants.add(path)

    @rule(path=paths)
    def read(self, path):
        assert self.sut.read(path) == model_read(self.files, self.grants, path)

    @invariant()
    def grants_agree(self):
        assert self.sut.grants == self.grants


GovernedStore.TestCase.settings = settings(max_examples=200, stateful_step_count=20)
TestGovernedStore = GovernedStore.TestCase

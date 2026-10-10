"""S2: the clauses test replays each world once and checks all three budgets on it."""
p = "/Users/claygendron/Git/Repos/vfs/tests/storage/database/test_rights.py"
s = open(p).read()
old = '''@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
@pytest.mark.parametrize("parameter_budget", [4, 9, 2_099])
async def test_the_clauses_admit_exactly_what_the_rights_admit(layout: Layout, parameter_budget: int) -> None:
    rng = random.Random(60 + parameter_budget)
    for _ in range(WORLDS // 3):
        world = random_world(rng, layout)
        storage = await _replay(world)
        host = storage._host
        entry = host.tables.entry
        try:
            async with host.session_factory() as session:
                judged = select(entry.c.path, entry.c.owner_id, entry.c.everyone_level)
                stored = (await session.execute(judged)).mappings().all()
                for subjects in SUBJECT_SETS:
                    for level in ("read", "read_write"):
                        rights = resolve(world.closures(subjects), world.grants, level)
                        clauses = visibility_clauses(entry, rights, host.profile, parameter_budget)
                        wanted = {row["path"] for row in stored if _admits(rights, row)}
                        if clauses is None:
                            assert wanted == {row["path"] for row in stored}
                            continue
                        got: set[str] = set()
                        for clause in clauses:
                            got |= set((await session.execute(select(entry.c.path).where(clause.predicate))).scalars())
                        assert got == wanted, (world, subjects, level, parameter_budget)
        finally:
            await storage.close()
'''
new = '''@pytest.mark.parametrize("layout", LAYOUTS, ids=["base", "siblings"])
async def test_the_clauses_admit_exactly_what_the_rights_admit(layout: Layout) -> None:
    rng = random.Random(60)
    for _ in range(WORLDS // 3):
        world = random_world(rng, layout)
        storage = await _replay(world)
        host = storage._host
        entry = host.tables.entry
        try:
            async with host.session_factory() as session:
                judged = select(entry.c.path, entry.c.owner_id, entry.c.everyone_level)
                stored = (await session.execute(judged)).mappings().all()
                for subjects in SUBJECT_SETS:
                    for level in ("read", "read_write"):
                        rights = resolve(world.closures(subjects), world.grants, level)
                        wanted = {row["path"] for row in stored if _admits(rights, row)}
                        for parameter_budget in (4, 9, 2_099):
                            clauses = visibility_clauses(entry, rights, host.profile, parameter_budget)
                            if clauses is None:
                                assert wanted == {row["path"] for row in stored}
                                continue
                            got: set[str] = set()
                            for clause in clauses:
                                got |= set((await session.execute(select(entry.c.path).where(clause.predicate))).scalars())
                            assert got == wanted, (world, subjects, level, parameter_budget)
        finally:
            await storage.close()
'''
assert s.count(old) == 1
open(p, "w").write(s.replace(old, new))

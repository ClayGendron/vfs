"""S3 (full): the road-row check folds into the glob test's pass; the standalone road test goes."""
p = "/Users/claygendron/Git/Repos/vfs/tests/storage/database/test_rights.py"
s = open(p).read()
old_glob = '''                named = {str(o.path) for o in result.observations} - {"/"}
                assert named == _expected(world, subjects, "read"), (world, subjects)
        finally:
            await storage.close()


async def test_a_road_row_carries_its_name_and_kind_only() -> None:
    rng = random.Random(59)
    checked = 0
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            for subjects in SUBJECT_SETS:
                visible = _expected(world, subjects, "read")
                admitted = {p for p in PATHS if set_rank(world, subjects, p) >= LEVEL_RANK["read"]}
                for road in sorted(visible - admitted):
                    row = (await storage.stat(path=Path(road), authority=_authority(subjects))).one()
                    assert row.kind == "directory" and row.populated == frozenset({"path", "kind"})
                    checked += 1
        finally:
            await storage.close()
    assert checked > 0
'''
new_glob = '''                named = {str(o.path) for o in result.observations} - {"/"}
                visible = _expected(world, subjects, "read")
                assert named == visible, (world, subjects)
                admitted = {p for p in PATHS if set_rank(world, subjects, p) >= LEVEL_RANK["read"]}
                for road in sorted(visible - admitted):
                    row = (await storage.stat(path=Path(road), authority=_authority(subjects))).one()
                    assert row.kind == "directory" and row.populated == frozenset({"path", "kind"})
                    checked += 1
        finally:
            await storage.close()
    assert checked > 0
'''
assert s.count(old_glob) == 1
s = s.replace(old_glob, new_glob)
old_head = '''async def test_glob_names_exactly_the_visible_rows_and_their_road() -> None:
    rng = random.Random(58)
    for _ in range(WORLDS):'''
new_head = '''async def test_glob_names_exactly_the_visible_rows_and_their_road() -> None:
    rng = random.Random(58)
    checked = 0
    for _ in range(WORLDS):'''
assert s.count(old_head) == 1
open(p, "w").write(s.replace(old_head, new_head))

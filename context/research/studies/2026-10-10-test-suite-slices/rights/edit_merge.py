"""S3: the glob test and the road-row test share one pass over one world set."""
p = "/Users/claygendron/Git/Repos/vfs/tests/storage/database/test_rights.py"
s = open(p).read()
old = '''async def test_a_road_row_carries_its_name_and_kind_only() -> None:
    rng = random.Random(59)
    checked = 0
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            for subjects in SUBJECT_SETS:
                visible = _expected(world, subjects, "read")
'''
new = '''async def test_a_road_row_carries_its_name_and_kind_only() -> None:
    rng = random.Random(58)
    checked = 0
    for _ in range(WORLDS):
        world = random_world(rng)
        storage = await _replay(world)
        try:
            for subjects in SUBJECT_SETS:
                result = await storage.glob(patterns=("/**",), authority=_authority(subjects))
                assert result.success is True, (subjects, result.errors)
                named = {str(o.path) for o in result.observations} - {"/"}
                assert named == _expected(world, subjects, "read"), (world, subjects)
                visible = _expected(world, subjects, "read")
'''
assert s.count(old) == 1
open(p, "w").write(s.replace(old, new))

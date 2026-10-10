import asyncio, cProfile, pstats
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage
async def main():
    for _ in range(40):
        fs = VirtualFileSystem(storage=InMemoryStorage())
        await fs.write(path="/a.txt", content="a")
        await fs.close()
pr = cProfile.Profile(); pr.enable(); asyncio.run(main()); pr.disable()
p = pstats.Stats(pr); p.sort_stats("cumulative")
p.print_stats(r"_first_touch|_verify_or_provision|_probe_sqlite_vec|create_all|_load_sqlite_vec|build_vfs_tables|seam.py.*__init__|metadata.*version|_apply_file_settings|\(write\)|\(close\)|_ensure_schema|run_sync")

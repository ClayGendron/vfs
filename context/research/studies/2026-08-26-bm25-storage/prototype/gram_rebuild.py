"""Force a whole gram-epoch rebuild (lexical build no-op'd) on an already-loaded store and time it."""
import asyncio, sqlite3, sys, time
from vfs.storage.backends.database import DatabaseStorage, indexing

DB = sys.argv[1]

async def main():
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    async def no_lexical(session, tables, epoch, executor):
        return None
    indexing.build_lexical_epoch = no_lexical
    indexing.INDEX_FORMAT_VERSION = 99  # force the whole rebuild through the format half
    t0 = time.perf_counter()
    result = await storage.reindex()
    wall = time.perf_counter() - t0
    assert result.success, result.errors
    print(f"gram epoch rebuild (verb wall, lexical skipped): {wall:.1f}s")
    await storage.close()
    con = sqlite3.connect(DB)
    print(con.execute("SELECT COUNT(*), SUM(LENGTH(postings)), SUM(doc_count) FROM vfs_grams_posting_list").fetchone())

asyncio.run(main())

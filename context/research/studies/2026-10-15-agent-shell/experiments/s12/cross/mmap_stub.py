# Spike s12 stand-in for the stdlib `mmap` on wasm32-wasip1 (preview1 has no memory mapping; CPython-WASI omits the module).
# pandas 3.0.6 imports mmap unconditionally (pandas/io/common.py:27) and uses mmap.mmap only when read_csv(memory_map=True).
ACCESS_READ, ACCESS_WRITE, ACCESS_COPY = 1, 2, 3
PAGESIZE = ALLOCATIONGRANULARITY = 65536

class mmap:
    def __init__(self, *args, **kwargs):
        raise OSError("mmap is unavailable on wasm32-wasi")

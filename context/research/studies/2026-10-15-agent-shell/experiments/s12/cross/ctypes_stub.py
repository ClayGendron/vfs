# Spike s12 stand-in for the stdlib `ctypes` on wasm32-wasip1 (no _ctypes: wasi-sdk has no libffi).
# pandas 3.0.6 imports ctypes unconditionally (pandas/errors/__init__.py:8) and uses only ctypes.WinError() on Windows.
def WinError(*args, **kwargs):
    raise OSError("ctypes is unavailable on wasm32-wasi")

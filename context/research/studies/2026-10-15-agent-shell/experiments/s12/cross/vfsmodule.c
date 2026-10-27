/* The `vfs` builtin module for spike s12: the verb door plus the numpy inittab registration.
 *
 * vfs.ping(n) calls one custom wasm import, `vfs.ping`, that the host binds with Linker.define_func;
 * the constructor runs from __wasm_call_ctors before main(), i.e. before Py_Initialize, which is the
 * only time PyImport_AppendInittab may be called. Builtin lookup compares the full dotted name, so
 * numpy's extension modules register under their dotted import names and need no .so on any path.
 */
#include <Python.h>

__attribute__((import_module("vfs"), import_name("ping")))
extern int32_t vfs_host_ping(int32_t n);

static PyObject *
vfs_ping(PyObject *self, PyObject *arg)
{
    long n = PyLong_AsLong(arg);
    if (n == -1 && PyErr_Occurred()) {
        return NULL;
    }
    return PyLong_FromLong(vfs_host_ping((int32_t)n));
}

static PyMethodDef vfs_methods[] = {
    {"ping", vfs_ping, METH_O, "ping(n) -> host value: one round trip through the custom wasm import vfs.ping"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef vfs_module = {PyModuleDef_HEAD_INIT, "vfs", "vfs verb door (spike)", 0, vfs_methods};

PyMODINIT_FUNC
PyInit_vfs(void)
{
    return PyModuleDef_Init(&vfs_module);
}

#ifdef VFS_WITH_NUMPY
#define NUMPY_MODULES(X) \
    X("numpy._core._multiarray_umath", PyInit__multiarray_umath) \
    X("numpy.linalg.lapack_lite", PyInit_lapack_lite) \
    X("numpy.linalg._umath_linalg", PyInit__umath_linalg) \
    X("numpy.fft._pocketfft_umath", PyInit__pocketfft_umath) \
    X("numpy.random._bounded_integers", PyInit__bounded_integers) \
    X("numpy.random._common", PyInit__common) \
    X("numpy.random._mt19937", PyInit__mt19937) \
    X("numpy.random._philox", PyInit__philox) \
    X("numpy.random._pcg64", PyInit__pcg64) \
    X("numpy.random._sfc64", PyInit__sfc64) \
    X("numpy.random.bit_generator", PyInit_bit_generator) \
    X("numpy.random._generator", PyInit__generator) \
    X("numpy.random.mtrand", PyInit_mtrand)
#define DECLARE(name, init) extern PyObject *init(void);
NUMPY_MODULES(DECLARE)
static int vfs_registered = 0;
__attribute__((constructor)) static void
vfs_register_numpy(void)
{
    /* Idempotent: a Wizer snapshot carries this flag, and _start runs the constructors again after it. */
    if (vfs_registered) {
        return;
    }
    vfs_registered = 1;
#define APPEND(name, init) PyImport_AppendInittab(name, init);
    NUMPY_MODULES(APPEND)
}
#endif

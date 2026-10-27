/* python.wasm entry point with a Wizer pre-initialization hook (spike s12).
 *
 * `wizer.initialize` (run once at build time by Wizer, with the stdlib zip preopened) initializes the interpreter and
 * imports the modules named in VFS_PREIMPORT; Wizer then snapshots linear memory. `main` (run on every `_start`)
 * finds the interpreter already live and executes `-c code` / a script path from argv, or stdin.  Without Wizer the
 * same binary works too: main initializes lazily.
 */
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wasi/api.h>

#ifndef VFS_PREIMPORT
#define VFS_PREIMPORT "import encodings, io, os, sys, json, csv, re"
#endif

/* Built as a WASI *reactor* (-mexec-model=reactor): the runtime's _initialize runs the constructors exactly once,
 * wizer.initialize snapshots a live interpreter, and vfs_run is the per-call entry. There is no _start, so nothing
 * re-runs the constructors after the snapshot (the command-model attempt crashed in libc++'s static destructors). */

static int initialized = 0;

static void
init_interpreter(void)
{
    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.parse_argv = 0;
    config.write_bytecode = 0;
    static wchar_t prog[] = L"/usr/local/bin/python.wasm";
    PyConfig_SetString(&config, &config.program_name, prog);
    PyStatus status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        Py_ExitStatusException(status);
    }
    initialized = 1;
}

__attribute__((export_name("wizer.initialize")))
void
wizer_initialize(void)
{
    init_interpreter();
    if (PyRun_SimpleString(VFS_PREIMPORT) != 0) {
        PyErr_Print();
    }
    PyRun_SimpleString("import gc; gc.collect(); gc.freeze()");
}

__attribute__((export_name("vfs_run")))
int
vfs_run(void)
{
    if (!initialized) {
        init_interpreter();
    }
    size_t argc = 0, buf_size = 0;
    if (__wasi_args_sizes_get(&argc, &buf_size) != 0) {
        return 70;
    }
    char **argv = calloc(argc + 1, sizeof(char *));
    char *buf = malloc(buf_size + 1);
    if (argv == NULL || buf == NULL || __wasi_args_get((uint8_t **)argv, (uint8_t *)buf) != 0) {
        return 70;
    }
    int rc = 0;
    size_t i = 1;
    while (i < argc && argv[i][0] == '-' && strcmp(argv[i], "-c") != 0) {
        i += (strcmp(argv[i], "-X") == 0) ? 2 : 1;   /* -I, -X utf8 and friends: the config is isolated already */
    }
    if (i + 1 < argc && strcmp(argv[i], "-c") == 0) {
        rc = PyRun_SimpleString(argv[i + 1]);
    } else if (i < argc) {
        FILE *fp = fopen(argv[i], "rb");
        if (fp == NULL) {
            perror(argv[i]);
            rc = 2;
        } else {
            rc = PyRun_SimpleFileEx(fp, argv[i], 1);
        }
    } else {
        rc = PyRun_SimpleFile(stdin, "<stdin>");
    }
    PyRun_SimpleString("import sys; sys.stdout.flush(); sys.stderr.flush()");   /* Python's own buffers, not just C stdio */
    fflush(stdout);
    fflush(stderr);
    free(argv);
    free(buf);
    return rc == 0 ? 0 : 1;
}

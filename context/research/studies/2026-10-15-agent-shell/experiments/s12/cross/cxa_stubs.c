/* C++ exception ABI stubs for wasm32-wasip1 (spike s12).
 *
 * clang compiles `throw` to __cxa_allocate_exception + __cxa_throw and compiles `catch` away when the target has no
 * unwinder; wasi-sdk 24's libc++abi defines neither symbol. pocketfft (numpy.fft) throws only on plan sizes numpy has
 * already validated, so here a throw reports and terminates: the guest traps instead of unwinding.
 */
#include <stdio.h>
#include <stdlib.h>

void *__cxa_allocate_exception(size_t size) { return malloc(size); }

void __cxa_throw(void *thrown, void *tinfo, void (*dest)(void *))
{
    (void)thrown; (void)tinfo; (void)dest;
    fputs("fatal: C++ exception thrown in python.wasm (no unwinder on wasm32-wasip1)\n", stderr);
    abort();
}

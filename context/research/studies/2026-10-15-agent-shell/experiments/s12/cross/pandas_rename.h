/* Rename header for the pandas cross build (spike s12), injected with -include into every pandas TU.
 * pandas vendors numpy's datetime helpers (pandas/_libs/src/vendored/numpy/datetime/np_datetime.c) with numpy's
 * original global names; as shared objects they never meet numpy's copies, in one static python.wasm they do
 * (wasm-ld: duplicate symbol). pandas' copies get a pd_ prefix; numpy keeps the originals. */
#define is_leapyear pd_is_leapyear
#define add_minutes_to_datetimestruct pd_add_minutes_to_datetimestruct
#define get_datetimestruct_days pd_get_datetimestruct_days

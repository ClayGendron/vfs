import os, sys, json
print('python', sys.version.split()[0], sys.platform, sys.prefix, sys.path[:3])
print(open('/data/hello.txt').read(), end='')
with open('/data/py.out', 'w') as f: f.write('written by cpython\n')
print(sorted(os.listdir('/data')))
print(os.stat('/data/hello.txt').st_size, oct(os.stat('/data/hello.txt').st_mode))
os.mkdir('/data/pydir'); os.rename('/data/py.out', '/data/pydir/moved.out'); os.remove('/data/pydir/moved.out'); os.rmdir('/data/pydir')
print(sorted(sys.builtin_module_names)[:8], len(sys.builtin_module_names))
print(json.dumps({'ok': True}))

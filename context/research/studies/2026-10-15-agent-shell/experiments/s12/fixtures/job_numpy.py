# Step 4 job: a CSV row read from vfs with numpy's own loader, a result written back as a row.
import os
import numpy as np
os.makedirs('/out', exist_ok=True)   # the shim's write-on-close has no `parents`; a program creates its own output dir
data = np.loadtxt('/data/sales.csv', delimiter=',', skiprows=1, usecols=(1, 2))
regions = np.loadtxt('/data/sales.csv', delimiter=',', skiprows=1, usecols=(0,), dtype=str)
print('rows', data.shape, 'regions', sorted(set(regions.tolist())))
out = []
for r in sorted(set(regions.tolist())):
    s = data[regions == r, 1]
    out.append((r, s.sum(), s.mean(), s.max()))
    print(r, round(float(s.sum()), 2), round(float(s.mean()), 2), float(s.max()))
np.savetxt('/out/summary.csv', np.array([[o[1], o[2], o[3]] for o in out]), delimiter=',', header='sum,mean,max', comments='', fmt='%.2f')
with open('/out/summary.csv') as f:
    print(f.read(), end='')

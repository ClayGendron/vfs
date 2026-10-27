# The agent's program. It runs unchanged under Pyodide (over VFSFS) and under native
# CPython in a container (over a 9P mount). It only ever sees a filesystem.
import io
import os
import sys

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("agg")
import matplotlib.pyplot as plt

root = os.environ.get("VFS_ROOT", "/vfs")
df = pd.read_csv(f"{root}/data/sales.csv")
summary = df.groupby("region")["sales"].agg(["sum", "mean", "max"])
print("rows:", len(df), "regions:", list(summary.index))
print(summary.to_string())

fig, ax = plt.subplots(figsize=(5, 3), dpi=100)
for region, g in df.groupby("region"):
    ax.plot(g["month"], g["sales"], label=region)
ax.legend(); ax.set_title("sales by month")
fig.savefig(f"{root}/out/plot.png", format="png")
plt.close(fig)

summary.to_csv(f"{root}/out/summary.csv")
with open(f"{root}/out/plot.png", "rb") as f:
    head = f.read(8)
print("png magic ok:", head == b"\x89PNG\r\n\x1a\n", "size:", os.path.getsize(f"{root}/out/plot.png"))
print("listing /out:", sorted(os.listdir(f"{root}/out")))
print("platform:", sys.platform, "numpy", np.__version__, "pandas", pd.__version__, "mpl", matplotlib.__version__)

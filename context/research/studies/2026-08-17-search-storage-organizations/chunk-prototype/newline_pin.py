"""Pin (step 3a): does build_code_gram_query emit any gram containing 0x0A
for the 12 scoped-bench patterns or the 25 unscoped ladder patterns?"""
import json

from vfs.models.code_grams import GramOr, build_code_gram_query, unpack_gram

SCOPED = [
    ("EXPORT_SYMBOL_GPL", False), ("kzalloc", False), ("mutex_lock", False),
    ("copyright", False), ("napi_gro_receive", False), ("GFP_KERNEL", False),
    ("cgroup_subsys_state", False), ("cgroup_subsys_state", False),
    ("spin_lock", False), ("napi_gro_receive", False), ("probe", False), ("obj-", False),
]
UNSCOPED = [
    ("xyzzy_no_such_symbol_42", False), ("randomize_kstack_offset", False),
    ("raw_spin_lock_irqsave", False), ("napi_gro_receive", False),
    ("cgroup_subsys_state", False), ("EXPORT_SYMBOL_GPL", False), ("kmalloc", False),
    ("GFP_KERNEL", False), ("static int __init", False), ("!= NULL", True),
    ("if (ret < 0)", True), (r"mutex_lock\(&", False),
    (r"static\s+int\s+\w+_probe", False), (".*alloc_page.*", False),
    ("copyright", False), ("deadlock", False), ("kfree", False), ("pr_debug", False),
    ("TODO|FIXME", False), ("kzalloc|kcalloc", False), ("devm_(kzalloc|kmalloc)", False),
    ("^(EXPORT_SYMBOL|MODULE_LICENSE)", False), ("^#include <linux/module.h>", False),
    ("ext[234]", False), ("-O[0-3]", False),
]

def all_grams(plan):
    if isinstance(plan, GramOr):
        out = set()
        for b in plan.branches:
            out |= all_grams(b)
        return out
    return plan.required_grams()

rows = []
any_newline = False
for pattern, fixed in dict.fromkeys(SCOPED + UNSCOPED):
    plan = build_code_gram_query(pattern, fixed_strings=fixed)
    grams = all_grams(plan)
    nl = sorted(unpack_gram(g).decode("latin1") for g in grams if 0x0A in unpack_gram(g))
    if nl:
        any_newline = True
    rows.append({"pattern": pattern, "fixed": fixed, "n_grams": len(grams),
                 "is_any": plan.is_any(), "newline_grams": nl})
for r in rows:
    flag = f"NEWLINE {r['newline_grams']}" if r["newline_grams"] else ""
    print(f"{r['pattern']!r:42s} grams={r['n_grams']:3d} any={r['is_any']} {flag}")
print()
print("PIN: any pattern emits a newline-bearing gram?", any_newline)
json.dump({"any_newline_gram": any_newline, "rows": rows}, open("newline_pin.json", "w"), indent=2)

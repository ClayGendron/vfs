"""The index fold is full casefolding; the HIR carries the pattern's literal unfolded. Literals whose fold changes length."""
from vfs.models.code_grams import fold_content, grams_for_fixed_string, unique_code_grams
for lit in ["straße", "ﬁle_ops", "ΣΟΦΟΣ", "İnit"]:
    raw_grams = unique_code_grams(lit, folded=False)
    print(f"{lit!r:14} fold {fold_content(lit)!r:14} grams of the literal as written absent from its folded grams: {len(raw_grams - grams_for_fixed_string(lit))} of {len(raw_grams)}")

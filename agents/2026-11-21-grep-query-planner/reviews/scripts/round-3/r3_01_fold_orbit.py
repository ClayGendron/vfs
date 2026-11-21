"""Does the index fold (Python casefold + Turkic-i) unify every pair the Rust matcher's (?i) treats as equal?

For each cased codepoint c known to this Python, the Rust matcher compiled
insensitive over the escaped literal c is run over a body holding every
codepoint 0..0x2FFFF (surrogates skipped), one per line. Every matched
codepoint d != c must satisfy fold_content(c) == fold_content(d), or a
case-insensitive grep for c can never nominate a body holding only d.
"""

import re
import sys
import unicodedata

from vfs.models.code_grams import fold_content
from vfs.pattern_matching import compile_verifier

print("python", sys.version.split()[0], "unicodedata", unicodedata.unidata_version)
cps = [cp for cp in range(0x30000) if not 0xD800 <= cp <= 0xDFFF and cp != 0x0A and cp != 0x0D]
body = "\n".join(chr(cp) for cp in cps) + "\n"
line_cp = {i + 1: cp for i, cp in enumerate(cps)}
cased = [
    cp
    for cp in cps
    if chr(cp).lower() != chr(cp) or chr(cp).upper() != chr(cp) or chr(cp).casefold() != chr(cp)
    or unicodedata.category(chr(cp)) in ("Ll", "Lu", "Lt")
    or (unicodedata.category(chr(cp)) == "Cn" and (0xA7C0 <= cp <= 0xA7FF or 0x1C80 <= cp <= 0x1C8F or 0x10D40 <= cp <= 0x10D8F))
]
print("cased candidates", len(cased))
violations = []
matched_other = 0
for cp in cased:
    m = compile_verifier(re.escape(chr(cp)), fixed_strings=False, word_regexp=False, case_mode="insensitive")
    rows, _ = m.hit_lines([body], before=0, after=0, cap=None, invert=False, budget=None)
    for _s, _e, line, _content in rows[0]:
        d = line_cp[line]
        matched_other += d != cp
        if d != cp and fold_content(chr(cp)) != fold_content(chr(d)):
            violations.append((cp, d))
print("matched pairs c != d (sanity)", matched_other)
print("violating pairs", len(violations))
for cp, d in violations[:40]:
    print(
        f"  U+{cp:04X} {unicodedata.name(chr(cp), '?')!s:40} ~ U+{d:04X} {unicodedata.name(chr(d), '<unassigned in this Python>')}"
        f"  fold {fold_content(chr(cp))!r} vs {fold_content(chr(d))!r}"
    )

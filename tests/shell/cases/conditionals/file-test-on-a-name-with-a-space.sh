# tier: language
# world: seed
f="with space.txt"
[[ -f $f ]]; echo "[[ unquoted: $?"
[ -f "$f" ]; echo "[ quoted: $?"
[ -f $f ] 2>/dev/null; echo "[ unquoted: $?"

# tier: language
# world: none
set -e
if [[ -e missing ]]; then echo "exists"; else echo "missing, no exit"; fi
[ -e missing ] || echo "or-list keeps going"
echo "end"

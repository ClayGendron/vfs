# tier: language
# world: none
{ echo o1; echo e1 >&2; echo o2; echo e2 >&2; } > o.txt 2> e.txt
mapfile -t o < o.txt; mapfile -t e < e.txt
echo "out=${o[*]} err=${e[*]}"

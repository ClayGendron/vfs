# tier: language
# world: none
arr=(g1 g2)
f() { local arr=(l1 l2 l3); echo "in f: ${#arr[@]} ${arr[*]}"; }
f
echo "after: ${#arr[@]} ${arr[*]}"

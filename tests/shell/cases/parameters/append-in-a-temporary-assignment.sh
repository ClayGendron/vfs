# tier: language
# world: none
s=base
f() { echo "in f: $s"; }
s+=more f
echo "after: $s"

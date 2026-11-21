# tier: language
# world: none
readonly r=1
f() { r=2; echo "status in f: $?"; }
f
echo "after f"

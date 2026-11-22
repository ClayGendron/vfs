# tier: language
# world: none
inner() { echo "inner start"; return 4; echo "inner unreachable"; }
outer() { inner; echo "inner gave $?"; echo "outer continues"; }
outer
echo "outer gave $?"

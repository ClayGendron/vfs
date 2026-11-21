# tier: language
# world: none
check() { [ "$1" -gt 5 ] 2>/dev/null; echo "$1 -> $?"; }
check 7
check 3
check seven

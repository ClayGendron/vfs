# tier: language
# world: none
f() { return "$1"; }
f 256; echo "256 -> $?"
f 300; echo "300 -> $?"
f -1; echo "-1 -> $?"

# tier: language
# world: none
f() { return "$1"; }
f 256; echo "256 -> $?"
f 257; echo "257 -> $?"
f -1; echo "-1 -> $?"
f 255; echo "255 -> $?"

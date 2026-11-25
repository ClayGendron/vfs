# tier: language
# world: none
f() { echo out; echo err >&2; }
f 2> err.txt
read -r e < err.txt
echo "err=$e"

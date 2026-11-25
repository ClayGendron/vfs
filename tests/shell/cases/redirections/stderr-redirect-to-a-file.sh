# tier: language
# world: none
{ echo to-stdout; echo to-stderr >&2; } 2> err.txt
IFS= read -r e < err.txt
echo "err file: $e"

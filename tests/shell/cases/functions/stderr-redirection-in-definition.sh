# tier: language
# world: none
warn() { echo "warning: $1" >&2; echo "to stdout"; } 2> err.txt
warn disk
IFS= read -r line < err.txt
echo "err.txt has: $line"

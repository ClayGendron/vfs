# tier: language
# world: none
set -o posix
x=1
x=2 :
echo "after colon in posix mode: $x"

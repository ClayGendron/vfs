# tier: language
# world: none
set -u
x=$(( 1 + 2 ))
echo "x=$x"
echo "$(( nosuch + 1 ))"
echo "not reached"

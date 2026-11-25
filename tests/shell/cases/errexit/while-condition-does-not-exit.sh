# tier: language
# world: none
set -e
n=0
while [ "$n" -lt 2 ]; do n=$((n + 1)); echo "n=$n"; done
echo "loop ended status=$?"

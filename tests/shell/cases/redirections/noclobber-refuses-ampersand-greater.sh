# tier: language
# world: none
echo original > f
set -C
{ echo out; echo err >&2; } &> f
echo "status=$?"
read -r x < f
echo "x=$x"

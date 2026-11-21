# tier: language
# world: none
echo original > f
set -C
echo replaced > f
echo "status=$?"
read -r x < f
echo "x=$x"

# tier: language
# world: none
echo original > f
set -C
echo blocked > f 2>/dev/null
set +C
echo allowed > f
read -r x < f
echo "x=$x"

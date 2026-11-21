# tier: language
# world: none
echo original > f
set -C
echo forced >| f
echo "status=$?"
read -r x < f
echo "x=$x"

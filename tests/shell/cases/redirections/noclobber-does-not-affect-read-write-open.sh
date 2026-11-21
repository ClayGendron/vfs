# tier: language
# world: none
echo original > f
set -C
read -r x <> f
echo "status=$? x=$x"

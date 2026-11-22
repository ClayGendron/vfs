# tier: language
# world: none
echo same 1>&1 > f
read -r x < f
echo "x=$x"

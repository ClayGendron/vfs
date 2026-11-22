# tier: language
# world: none
echo via-fd-one 1> f
read -r x < f
echo "x=$x"

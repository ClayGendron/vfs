# tier: language
# world: none
echo payload 3> f >&3
read -r x < f
echo "x=$x"

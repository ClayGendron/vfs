# tier: language
# world: none
echo ten 10> f >&10
read -r x < f
echo "x=$x"

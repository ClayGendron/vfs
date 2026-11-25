# tier: language
# world: none
echo via-dev-fd 3> f >/dev/fd/3
read -r x < f
echo "x=$x"

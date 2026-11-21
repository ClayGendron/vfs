# tier: language
# world: none
echo via-fd-zero > f
read -r x 0< f
echo "x=$x"

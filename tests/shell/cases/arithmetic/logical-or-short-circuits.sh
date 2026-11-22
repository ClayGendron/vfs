# tier: language
# world: none
x=0
echo "$((1 || (x = 1))) x=$x"
echo "$((0 || (x = 3))) x=$x"

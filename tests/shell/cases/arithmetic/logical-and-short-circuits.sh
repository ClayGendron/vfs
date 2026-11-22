# tier: language
# world: none
x=0
echo "$((0 && (x = 1))) x=$x"
echo "$((1 && (x = 2))) x=$x"

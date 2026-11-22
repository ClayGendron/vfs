# tier: language
# world: none
x=$'ab\0cd'
echo "[$x] len=${#x}"
y=$'ab\x00cd'
echo "[$y] len=${#y}"

# tier: language
# world: none
a=(a b c d e)
echo "-2 -> ${a[@]: -2}"
echo "-3:2 -> ${a[@]: -3:2}"
echo "(-1) -> ${a[@]:(-1)}"

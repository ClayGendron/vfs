# tier: language
# world: none
x=12
(( x &= 10 )); echo "x=$x"
(( x |= 5 )); echo "x=$x"
(( x ^= 15 )); echo "x=$x"

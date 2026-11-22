# tier: language
# world: none
positive() (( $1 > 0 ))
positive 5; echo "5 -> $?"
positive -2; echo "-2 -> $?"

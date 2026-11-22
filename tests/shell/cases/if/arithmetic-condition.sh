# tier: language
# world: none
if (( 2 > 1 )); then echo "2 > 1"; fi
if (( 0 )); then echo "wrong"; else echo "(( 0 )) is false"; fi
n=3
if (( n % 2 )); then echo "$n is odd"; fi

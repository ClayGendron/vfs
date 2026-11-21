# tier: language
# world: none
x=3
[[ ( $x -eq 1 || $x -eq 3 ) && ( -n $x ) ]]; echo "grouped: $?"
[[ (($x -eq 3)) ]]; echo "double parens inside: $?"

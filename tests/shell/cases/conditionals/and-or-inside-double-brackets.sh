# tier: language
# world: none
x=5
[[ $x -gt 1 && $x -lt 10 ]]; echo "and: $?"
[[ $x -gt 7 || $x -eq 5 ]]; echo "or: $?"
[[ $x -gt 7 && $x -eq 5 ]]; echo "and false: $?"

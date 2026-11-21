# tier: language
# world: none
x=5
[[ 1+1 -eq 2 ]]; echo "1+1 -eq 2: $?"
[[ x -eq 5 ]]; echo "x -eq 5: $?"
[[ x*2 -gt 9 ]]; echo "x*2 -gt 9: $?"
[[ "" -eq 0 ]]; echo "empty -eq 0: $?"
[[ no_such_var -eq 0 ]]; echo "unset name -eq 0: $?"

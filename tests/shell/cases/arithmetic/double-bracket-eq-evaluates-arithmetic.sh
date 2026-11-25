# tier: language
# world: none
x=3
[[ 1+2 -eq 3 ]] && echo "sum equal"
[[ x -eq 3 ]] && echo "name evaluated"
[[ x*2 -gt 5 ]] && echo "product greater"

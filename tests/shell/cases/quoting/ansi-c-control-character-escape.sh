# tier: language
# world: none
x=$'\cA'
echo "len=${#x}"
[ "$x" = $'\001' ] && echo "cA is 001"
[ $'\c[' = $'\e' ] && echo "c[ is escape"

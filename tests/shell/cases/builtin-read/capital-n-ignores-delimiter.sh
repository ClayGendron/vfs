# tier: language
# world: none
read -N 5 x <<< $'ab\ncdef'
printf 'x=%q\n' "$x"

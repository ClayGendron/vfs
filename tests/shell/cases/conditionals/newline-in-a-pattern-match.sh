# tier: language
# world: none
s=$'two\nlines'
[[ $s == *$'\n'* ]] && echo "has a newline"
[[ $s == two* ]] && echo "star crosses the newline"

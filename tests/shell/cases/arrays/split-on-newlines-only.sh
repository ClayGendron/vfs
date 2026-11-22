# tier: language
# world: none
text=$'first line\nsecond line'
IFS=$'\n'
a=($text)
unset IFS
echo "count=${#a[@]}"
printf '[%s]\n' "${a[@]}"

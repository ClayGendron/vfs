# tier: language
# world: none
s=solo
declare -a s
declare -p s
s[1]=added
echo "count=${#s[@]} first=${s[0]}"

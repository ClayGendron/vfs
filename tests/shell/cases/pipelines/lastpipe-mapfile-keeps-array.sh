# tier: language
# world: none
shopt -s lastpipe
printf '%s\n' red green blue | mapfile -t colors
echo "count=${#colors[@]} second=${colors[1]}"

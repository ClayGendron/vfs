# tier: language
# world: none
printf 'a\nb\n' | mapfile -t arr
echo "count=${#arr[@]}"
shopt -s lastpipe
printf 'a\nb\n' | mapfile -t arr
echo "count=${#arr[@]}"

# tier: language
# world: none
mapfile -t -s 10 arr <<< $'a\nb'
echo "status=$? count=${#arr[@]}"

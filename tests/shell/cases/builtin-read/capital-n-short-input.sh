# tier: language
# world: none
read -N 10 x <<< "ab"
echo "status=$?"
printf 'x=%q\n' "$x"

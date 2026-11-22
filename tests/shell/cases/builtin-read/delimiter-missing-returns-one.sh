# tier: language
# world: none
read -d : x <<< "no colon here"
echo "status=$?"
printf 'x=%q\n' "$x"

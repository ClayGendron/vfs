# tier: language
# world: none
printf 'a\\tb\nc\\\nd\n' > f
IFS= read -r x < f
echo "raw=[$x]"
IFS= read x < f
echo "cooked=[$x]"

# tier: language
# world: none
false | true | (exit 3)
echo "${PIPESTATUS[@]}"
true
echo "${PIPESTATUS[@]}"
echo "count=${#PIPESTATUS[@]}"

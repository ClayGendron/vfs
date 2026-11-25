# tier: language
# world: none
IFS= read -r x <<< $'tab\there'
printf '%q\n' "$x"

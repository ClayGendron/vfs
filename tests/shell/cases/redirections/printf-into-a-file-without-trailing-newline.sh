# tier: language
# world: none
printf 'no newline' > f
IFS= read -r x < f
echo "read status=$? x=[$x]"

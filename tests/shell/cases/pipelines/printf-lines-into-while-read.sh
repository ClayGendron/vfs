# tier: language
# world: none
printf '%s\n' one two three | while IFS= read -r line; do
  echo "line=[$line]"
done

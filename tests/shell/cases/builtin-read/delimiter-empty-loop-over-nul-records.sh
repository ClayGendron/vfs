# tier: language
# world: none
printf '%s\0' "one" "two words" "three" | while IFS= read -r -d '' item; do
  echo "item=[$item]"
done

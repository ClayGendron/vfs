# tier: language
# world: none
while IFS=, read -r a b c; do
  echo "a=[$a] b=[$b] c=[$c]"
done <<< "x,,z"

# tier: language
# world: none
while read -r a b c; do
  echo "a=[$a] b=[$b] c=[$c]"
done <<< "only"

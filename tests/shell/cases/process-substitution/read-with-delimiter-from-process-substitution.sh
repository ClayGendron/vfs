# tier: language
# world: none
while IFS= read -r -d ',' item; do
  echo "item=[$item]"
done < <(printf 'a,b c,d,')

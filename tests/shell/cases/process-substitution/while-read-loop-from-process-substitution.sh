# tier: language
# world: none
while IFS= read -r line; do
  echo "line=[$line]"
done < <(printf 'one\ntwo words\n')

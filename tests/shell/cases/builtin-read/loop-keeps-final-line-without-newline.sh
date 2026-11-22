# tier: language
# world: none
printf 'one\ntwo' | while IFS= read -r line || [ -n "$line" ]; do
  echo "[$line]"
done

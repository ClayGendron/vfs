# tier: language
# world: none
printf 'one\ntwo' | while IFS= read -r line; do
  echo "[$line]"
done
echo "done"

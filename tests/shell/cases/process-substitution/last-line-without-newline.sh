# tier: language
# world: none
while IFS= read -r line || [ -n "$line" ]; do
  echo "[$line]"
done < <(printf 'a\nno-newline')

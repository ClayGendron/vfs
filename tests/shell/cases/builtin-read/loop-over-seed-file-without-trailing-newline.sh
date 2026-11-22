# tier: language
# world: seed
while IFS= read -r line || [ -n "$line" ]; do
  echo "[$line]"
done < data/nonl.txt

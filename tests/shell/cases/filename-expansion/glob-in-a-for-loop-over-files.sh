# tier: language
# world: seed
for f in docs/*.md; do
  IFS= read -r first < "$f"
  echo "$f: $first"
done

# tier: language
# world: none
for w in "one two" 'three  four' five; do
  printf '[%s]\n' "$w"
done

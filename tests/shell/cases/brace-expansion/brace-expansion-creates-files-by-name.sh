# tier: language
# world: none
for f in out.{1..3}; do
  echo "$f" > "$f"
done
[ -e out.1 ] && [ -e out.2 ] && [ -e out.3 ] && echo "three files"

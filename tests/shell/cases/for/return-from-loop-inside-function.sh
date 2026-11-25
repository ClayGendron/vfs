# tier: language
# world: none
find_first_big() {
  for n in "$@"; do
    if [ "$n" -gt 10 ]; then echo "found $n"; return 0; fi
  done
  return 1
}
find_first_big 3 12 40
echo "status=$?"
find_first_big 1 2
echo "status=$?"

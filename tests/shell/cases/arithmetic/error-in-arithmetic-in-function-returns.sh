# tier: language
# world: none
f() {
  (( 1 / 0 ))
  echo "after in f: $?"
}
f
echo "after f: $?"

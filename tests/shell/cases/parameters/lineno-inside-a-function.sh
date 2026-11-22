# tier: language
# world: none
f() {
  echo "in f: $LINENO"
}
f
echo "after: $LINENO"

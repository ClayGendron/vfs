# tier: language
# world: none
f() {
  echo "first"
  return 0
  echo "not reached"
}
f
echo "after f"

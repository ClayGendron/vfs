# tier: language
# world: none
set -e
f() {
  echo "in f"
  false
  echo "not reached in f"
}
f
echo "not reached"

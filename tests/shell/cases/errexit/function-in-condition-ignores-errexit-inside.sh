# tier: language
# world: none
set -e
f() {
  false
  echo "inside f after false"
}
if f; then echo "f succeeded"; fi
echo "continued"

# tier: language
# world: none
set -e
f() {
  local x
  x=$(false)
  echo "not reached"
}
f
echo "not reached"

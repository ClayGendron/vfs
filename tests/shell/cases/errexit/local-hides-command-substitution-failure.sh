# tier: language
# world: none
set -e
f() {
  local x=$(false)
  echo "survived x=[$x] status=$?"
}
f

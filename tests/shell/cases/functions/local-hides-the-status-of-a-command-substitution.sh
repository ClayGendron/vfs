# tier: language
# world: none
f() {
  local x=$(false)
  echo "local with substitution: $?"
  local y
  y=$(false)
  echo "plain assignment: $?"
}
f

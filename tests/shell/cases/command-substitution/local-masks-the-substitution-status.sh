# tier: language
# world: none
f() {
  local x=$(exit 3)
  echo "local: $?"
  local y
  y=$(exit 3)
  echo "separate: $?"
}
f

# tier: language
# world: none
f() {
  local -r fixed=1
  fixed=2
  echo "status=$? fixed=$fixed"
}
f
echo "after f status=$?"

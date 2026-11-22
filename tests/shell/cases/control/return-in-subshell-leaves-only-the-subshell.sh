# tier: language
# world: none
f() {
  ( return 3 )
  echo "after subshell status=$?"
  return 1
}
f
echo "f status=$?"

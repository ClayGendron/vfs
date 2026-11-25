# tier: language
# world: none
x=global
f() {
  local x=local
  echo "in f: $x"
}
f
echo "after f: $x"

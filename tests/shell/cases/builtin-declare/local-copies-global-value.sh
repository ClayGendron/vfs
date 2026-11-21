# tier: language
# world: none
x=start
f() {
  local x=$x
  x+=-changed
  echo "in f: $x"
}
f
echo "after f: $x"

# tier: language
# world: none
x=global
f() {
  local x
  echo "in f: [${x-unset}]"
  declare -p x
}
f
echo "after f: $x"

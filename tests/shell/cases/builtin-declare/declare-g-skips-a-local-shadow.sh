# tier: language
# world: none
x=global
f() {
  local x=local
  declare -g x=newglobal
  echo "in f: $x"
}
f
echo "after f: $x"

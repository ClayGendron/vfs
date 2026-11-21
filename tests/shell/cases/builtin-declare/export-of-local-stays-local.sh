# tier: language
# world: none
f() {
  local L=inner
  export L
  declare -p L
}
f
echo "after f: [${L-unset}]"

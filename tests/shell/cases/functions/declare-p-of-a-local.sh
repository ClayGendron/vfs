# tier: language
# world: none
f() {
  local plain=1
  local -i num=5
  local -a list=(a b)
  declare -p plain num list
}
f

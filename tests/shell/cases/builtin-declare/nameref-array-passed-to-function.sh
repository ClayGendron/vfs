# tier: language
# world: none
count() {
  local -n list=$1
  echo "$1 has ${#list[@]}: ${list[*]}"
}
fruits=(apple pear fig)
count fruits

# tier: language
# world: none
f() {
  echo "default: $*"
  local IFS=,
  echo "comma: $*"
  IFS=
  echo "empty: $*"
}
f a b "c d"

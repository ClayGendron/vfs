# tier: language
# world: none
parse() {
  local OPTIND opt
  while getopts xy opt; do echo "  $opt"; done
  shift $((OPTIND - 1))
  echo "  rest: $*"
}
echo "call 1"
parse -x one
echo "call 2"
parse -y two

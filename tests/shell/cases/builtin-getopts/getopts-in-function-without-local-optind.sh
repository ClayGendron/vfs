# tier: language
# world: none
parse() {
  while getopts xy opt; do echo "  $opt"; done
}
echo "call 1"
parse -x -y
echo "call 2 (OPTIND=$OPTIND)"
parse -x -y
echo "done"

# tier: language
# world: none
parse() {
  local OPTIND opt
  while getopts "ab:" opt; do
    case $opt in a) echo "flag a";; b) echo "b=$OPTARG";; esac
  done
  shift $(( OPTIND - 1 ))
  echo "rest: $*"
}
parse -a -b val file1
parse -b other file2

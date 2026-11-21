# tier: language
# world: none
kind() {
  case $1 in
    -*) echo "option $1" ;;
    *) echo "operand $1" ;;
  esac
}
kind -v; kind file

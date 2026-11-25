# tier: language
# world: none
check() {
  if [ -z "$1" ]; then
    return 1
  fi
  case $1 in
    a*) echo "starts with a" ;;
    *) echo other ;;
  esac
}
type check

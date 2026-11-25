# tier: language
# world: none
x=$(
  case "$1" in
    *) echo default
       ;;
  esac
)
echo "[$x]"

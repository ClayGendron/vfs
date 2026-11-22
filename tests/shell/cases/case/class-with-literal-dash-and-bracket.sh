# tier: language
# world: none
for c in - a ']' b; do
  case $c in
    [-a]) echo "[$c] in [-a]" ;;
    []]) echo "[$c] in []]" ;;
    *) echo "[$c] neither" ;;
  esac
done

# tier: language
# world: none
shopt -s extglob
for v in 42 4a "" 007; do
  case $v in
    +([0-9])) echo "[$v] integer" ;;
    *) echo "[$v] not integer" ;;
  esac
done

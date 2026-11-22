# tier: language
# world: none
for n in 7 42 100; do
  case $n in
    [0-9]) echo "$n: one digit" ;;
    [0-9][0-9]) echo "$n: two digits" ;;
    *) echo "$n: more" ;;
  esac
done

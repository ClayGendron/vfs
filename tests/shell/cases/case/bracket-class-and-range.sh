# tier: language
# world: none
for c in a m z 5 _; do
  case $c in
    [aeiou]) echo "$c: vowel" ;;
    [a-z]) echo "$c: other letter" ;;
    [0-9]) echo "$c: digit" ;;
    *) echo "$c: other" ;;
  esac
done

# tier: language
# world: none
for w in a ab abc; do
  case $w in
    ?) echo "$w: one char" ;;
    ??) echo "$w: two chars" ;;
    *) echo "$w: longer" ;;
  esac
done

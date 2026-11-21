# tier: language
# world: none
for w in yes y no maybe; do
  case $w in
    yes | y) echo "$w: affirmative" ;;
    no|n) echo "$w: negative" ;;
    *) echo "$w: unknown" ;;
  esac
done

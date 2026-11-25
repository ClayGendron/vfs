# tier: language
# world: none
shopt -s extglob
for w in ab aab b abb; do
  case $w in
    *(a)b) echo "$w: *(a)b" ;;
    ?(a)bb) echo "$w: ?(a)bb" ;;
    *) echo "$w: none" ;;
  esac
done

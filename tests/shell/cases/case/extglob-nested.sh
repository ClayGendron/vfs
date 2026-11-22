# tier: language
# world: none
shopt -s extglob
for w in abab ab abc; do
  case $w in
    +(ab)) echo "$w: repeated ab" ;;
    *) echo "$w: no" ;;
  esac
done

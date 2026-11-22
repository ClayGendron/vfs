# tier: language
# world: none
shopt -s extglob
for f in a.txt b.md c.log; do
  case $f in
    @(*.txt|*.md)) echo "$f: doc" ;;
    *) echo "$f: other" ;;
  esac
done

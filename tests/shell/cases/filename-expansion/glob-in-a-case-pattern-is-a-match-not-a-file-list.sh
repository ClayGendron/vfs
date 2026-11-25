# tier: language
# world: seed
for word in a.md notes.txt; do
  case $word in
    *.md) echo "$word: markdown" ;;
    *) echo "$word: other" ;;
  esac
done

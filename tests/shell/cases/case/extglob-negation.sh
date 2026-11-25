# tier: language
# world: none
shopt -s extglob
for f in app.log app.txt; do
  case $f in
    !(*.log)) echo "$f: not a log" ;;
    *) echo "$f: log" ;;
  esac
done

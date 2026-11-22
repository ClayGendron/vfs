# tier: language
# world: none
for f in report.txt notes.md archive.tar.gz README; do
  case $f in
    *.txt|*.md) echo "$f: text" ;;
    *.tar.*) echo "$f: tarball" ;;
    [A-Z]*) echo "$f: capitalised" ;;
  esac
done

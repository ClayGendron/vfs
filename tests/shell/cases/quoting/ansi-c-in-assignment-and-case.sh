# tier: language
# world: none
nl=$'\n'
s="a${nl}b"
printf '%s|\n' "$s"
case $'\t' in
  $'\t') echo "tab matched" ;;
  *) echo "no match" ;;
esac

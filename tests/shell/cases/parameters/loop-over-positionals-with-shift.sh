# tier: language
# world: none
set -- one 'two three' four
while [ $# -gt 0 ]; do
  echo "[$1]"
  shift
done
echo "left=$#"

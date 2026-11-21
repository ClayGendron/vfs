# tier: language
# world: none
set -- a 'b c' d
while [ $# -gt 0 ]; do
  printf '[%s] ' "$1"
  shift
done
echo "left=$#"

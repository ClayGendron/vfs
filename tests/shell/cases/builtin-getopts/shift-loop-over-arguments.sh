# tier: language
# world: none
set -- one "two words" three
while (( $# > 0 )); do
  echo "arg=[$1] left=$#"
  shift
done

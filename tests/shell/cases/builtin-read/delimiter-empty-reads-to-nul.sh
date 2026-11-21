# tier: language
# world: none
printf 'first\0second\0' | {
  IFS= read -r -d '' a
  IFS= read -r -d '' b
  echo "a=[$a] b=[$b]"
}

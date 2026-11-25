# tier: language
# world: none
s="a1 b22 c333"
while [[ $s =~ ([a-z])([0-9]+) ]]; do
  echo "${BASH_REMATCH[1]} -> ${BASH_REMATCH[2]}"
  s=${s#*"${BASH_REMATCH[0]}"}
done

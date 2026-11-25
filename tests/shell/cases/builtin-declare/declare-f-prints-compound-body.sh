# tier: language
# world: none
g() {
  if [ "$1" = a ]; then
    echo first
  else
    for i in 1 2; do echo "$i"; done | while read -r l; do echo "$l"; done
  fi
}
declare -f g

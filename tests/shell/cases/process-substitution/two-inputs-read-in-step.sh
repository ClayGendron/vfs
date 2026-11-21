# tier: language
# world: none
zip() {
  while read -r x <&3 && read -r y <&4; do
    echo "$x-$y"
  done 3< "$1" 4< "$2"
}
zip <(printf '1\n2\n3\n') <(printf 'a\nb\nc\n')

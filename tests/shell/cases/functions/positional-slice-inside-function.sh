# tier: language
# world: none
f() {
  printf '[%s]' "${@:2}"; echo
  printf '[%s]' "${@:1:2}"; echo
  printf '[%s]' "${@: -1}"; echo
}
f one two three four

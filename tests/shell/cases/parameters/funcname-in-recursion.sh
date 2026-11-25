# tier: language
# world: none
r() {
  if [ "$1" -gt 0 ]; then r $(( $1 - 1 )); else echo "${FUNCNAME[*]}"; fi
}
r 2

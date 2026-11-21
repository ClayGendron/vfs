# tier: language
# world: none
r() {
  if (( $1 > 0 )); then r $(( $1 - 1 )); return; fi
  echo "depth=${#FUNCNAME[@]} top=${FUNCNAME[0]} bottom=${FUNCNAME[-1]}"
}
r 3

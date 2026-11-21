# tier: language
# world: none
fact() {
  if (( $1 <= 1 )); then echo 1; return; fi
  local prev
  prev=$(fact $(( $1 - 1 )))
  echo $(( $1 * prev ))
}
for n in 0 1 5 10; do echo "$n! = $(fact $n)"; done

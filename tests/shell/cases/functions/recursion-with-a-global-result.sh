# tier: language
# world: none
fib() {
  if (( $1 < 2 )); then result=$1; return; fi
  local a
  fib $(( $1 - 1 )); a=$result
  fib $(( $1 - 2 ))
  result=$(( a + result ))
}
for n in 0 1 2 7 12; do fib $n; echo "fib($n)=$result"; done

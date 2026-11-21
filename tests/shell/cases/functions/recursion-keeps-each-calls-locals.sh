# tier: language
# world: none
countdown() {
  local n=$1
  (( n == 0 )) && { echo "liftoff"; return; }
  echo "down $n"
  countdown $(( n - 1 ))
  echo "back at $n"
}
countdown 3

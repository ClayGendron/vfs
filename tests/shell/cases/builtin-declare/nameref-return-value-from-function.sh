# tier: language
# world: none
set_result() {
  local -n out=$1
  out="computed for $2"
}
set_result answer alpha
echo "answer=$answer"

# tier: language
# world: none
inner() { echo "inner sees n=$n"; n=n+1; }
outer() {
  local -i n=5
  inner
  echo "outer n=$n"
}
outer
echo "top n=[${n-unset}]"

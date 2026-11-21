# tier: language
# world: none
x=global
inner() { unset x; echo "inner: [${x-unset}]"; }
outer() {
  local x=outer-local
  inner
  echo "outer: [${x-unset}]"
}
outer
echo "top: $x"

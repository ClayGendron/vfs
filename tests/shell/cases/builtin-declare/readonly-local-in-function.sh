# tier: language
# world: none
f() {
  local -r x=inner
  x=changed 2>/dev/null
  echo "in f: status=$? x=$x"
}
f
x=global
echo "outside: x=$x"

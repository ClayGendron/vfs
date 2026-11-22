# tier: language
# world: none
f() {
  local a=1 b c=3
  echo "a=$a b=[${b-unset}] c=$c"
}
a=A b=B c=C
f
echo "a=$a b=$b c=$c"

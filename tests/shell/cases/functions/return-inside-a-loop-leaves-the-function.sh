# tier: language
# world: none
f() {
  for i in 1 2 3 4; do
    if [ "$i" = 3 ]; then return "$i"; fi
    echo "i=$i"
  done
  echo "not reached"
}
f
echo "status=$?"

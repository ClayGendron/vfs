# tier: language
# world: none
f() {
  echo "body line $LINENO"
}
f
echo "call line $LINENO"

# tier: language
# world: none
f() {
  echo $(( 1 / 0 ))
  echo "rest of f"
}
f; echo "same line as the call"
echo "next line: $?"

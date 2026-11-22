# tier: language
# world: none
greet() {
  echo "hello, $1"
}
greet world
greet "two words"
echo "status=$?"

# tier: language
# world: none
function greet {
  echo "hello, $1"
}
greet world
echo "status=$?"

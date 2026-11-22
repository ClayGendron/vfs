# tier: language
# world: none
function greet() {
  echo "hello, $1"
}
function spaced () { echo "spaced $1"; }
greet world
spaced call

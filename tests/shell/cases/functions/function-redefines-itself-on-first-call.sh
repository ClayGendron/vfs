# tier: language
# world: none
init() {
  echo "initializing"
  init() { echo "already initialized"; }
}
init
init
init

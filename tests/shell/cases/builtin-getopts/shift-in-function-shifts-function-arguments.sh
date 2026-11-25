# tier: language
# world: none
f() {
  shift
  echo "in f: $*"
}
set -- top1 top2
f a b c
echo "top: $*"

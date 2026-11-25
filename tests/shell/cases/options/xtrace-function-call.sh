# tier: language
# world: none
f() { echo "in f $1"; }
{
  set -x
  f arg
  set +x
} 2>&1

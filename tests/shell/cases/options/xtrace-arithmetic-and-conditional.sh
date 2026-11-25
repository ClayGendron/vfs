# tier: language
# world: none
{
  set -x
  n=2
  (( n + 1 ))
  [[ $n == 2 ]]
  set +x
} 2>&1

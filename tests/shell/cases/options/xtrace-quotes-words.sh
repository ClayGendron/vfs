# tier: language
# world: none
{
  set -x
  echo "a b" 'c' '' "it's"
  set +x
} 2>&1

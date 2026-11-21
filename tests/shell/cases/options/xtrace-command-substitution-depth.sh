# tier: language
# world: none
{
  set -x
  echo "$(echo inner)"
  set +x
} 2>&1

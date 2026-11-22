# tier: language
# world: none
{
  set -x
  echo hi
  set +x
} 2>&1
echo "untraced"

# tier: language
# world: none
{
  set -x
  echo 'a*b' '$x' 'tab	here' 'new
line'
  set +x
} 2>&1

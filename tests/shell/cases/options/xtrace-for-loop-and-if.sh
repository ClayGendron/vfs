# tier: language
# world: none
{
  set -x
  for i in 1 2; do
    if [ "$i" = 2 ]; then echo two; fi
  done
  set +x
} 2>&1

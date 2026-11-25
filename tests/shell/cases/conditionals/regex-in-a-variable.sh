# tier: language
# world: none
re='^[0-9]+(\.[0-9]+)?$'
for v in 42 3.14 1. abc; do
  if [[ $v =~ $re ]]; then echo "$v: number"; else echo "$v: not a number"; fi
done

# tier: language
# world: none
is_even() { (( $1 == 0 )) && return 0; is_odd $(( $1 - 1 )); }
is_odd() { (( $1 == 0 )) && return 1; is_even $(( $1 - 1 )); }
for n in 0 3 8; do
  if is_even $n; then echo "$n even"; else echo "$n odd"; fi
done

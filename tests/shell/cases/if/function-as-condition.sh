# tier: language
# world: none
is_even() { (( $1 % 2 == 0 )); }
for n in 3 4; do
  if is_even "$n"; then echo "$n even"; else echo "$n odd"; fi
done

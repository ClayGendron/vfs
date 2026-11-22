# tier: language
# world: none
for n in 1 6 8 12 16; do
  if (( n > 0 && (n & (n - 1)) == 0 )); then echo "$n pow2"; else echo "$n no"; fi
done

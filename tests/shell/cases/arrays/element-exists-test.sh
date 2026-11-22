# tier: language
# world: none
a=([0]=x [2]="")
for i in 0 1 2 3; do
  if [[ -v a[$i] ]]; then echo "a[$i] set"; else echo "a[$i] not set"; fi
done

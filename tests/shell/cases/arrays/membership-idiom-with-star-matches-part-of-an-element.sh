# tier: language
# world: none
a=(apple "green pear" fig)
for w in fig pear "green pear"; do
  if [[ " ${a[*]} " == *" $w "* ]]; then echo "$w: found"; else echo "$w: not found"; fi
done

# tier: language
# world: none
for w in cat dog bird; do
  if [[ $w =~ ^(cat|dog)$ ]]; then echo "$w: pet"; else echo "$w: other"; fi
done

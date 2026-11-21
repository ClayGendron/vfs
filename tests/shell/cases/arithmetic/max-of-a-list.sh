# tier: language
# world: none
max=0
for n in 4 19 7 11; do
  (( n > max )) && max=$n
done
echo "max=$max"

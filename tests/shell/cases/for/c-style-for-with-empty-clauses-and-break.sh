# tier: language
# world: none
i=0
for ((;;)); do
  ((i++))
  ((i >= 3)) && break
done
echo "i=$i"

# tier: language
# world: none
n=0
for (( ; ; )); do
  (( n++ >= 2 )) && break
done
echo "n=$n"

# tier: language
# world: none
n=0
while read -r line; do n=$((n+1)); done < missing.txt
echo "status=$? n=$n"

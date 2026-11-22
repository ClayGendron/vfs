# tier: language
# world: none
n=5 sum=0
while ((n > 0)); do ((sum += n, n--)); done
echo "sum=$sum n=$n"

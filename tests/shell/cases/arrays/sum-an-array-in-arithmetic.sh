# tier: language
# world: none
nums=(3 5 10)
total=0
for n in "${nums[@]}"; do (( total += n )); done
echo "total=$total"
echo "direct=$(( nums[0] + nums[1] * nums[2] ))"

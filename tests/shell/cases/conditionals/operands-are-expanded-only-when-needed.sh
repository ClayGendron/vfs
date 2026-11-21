# tier: language
# world: none
n=0
[[ 1 -eq 2 && $(( n += 1 )) -eq 1 ]]
echo "after skipped and: n=$n"
[[ 1 -eq 1 || $(( n += 10 )) -eq 1 ]]
echo "after skipped or: n=$n"
[[ 1 -eq 1 && $(( n += 100 )) -gt 0 ]]
echo "after evaluated and: n=$n"

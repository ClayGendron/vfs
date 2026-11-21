# tier: language
# world: none
: > 'n=2x3'
let n=2*3
echo "status=$? n=${n-unset}"
let "n=2*3"
echo "n=$n"

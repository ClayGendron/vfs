# tier: language
# world: none
: > out.txt
[ -s out.txt ]; echo "after truncate: $?"
echo data > out.txt
[ -s out.txt ]; echo "after write: $?"
printf '' >> out.txt
[ -s out.txt ]; echo "after empty append: $?"

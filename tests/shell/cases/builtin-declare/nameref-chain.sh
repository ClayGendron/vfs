# tier: language
# world: none
c=end
declare -n b=c
declare -n a=b
echo "a=$a"
a=changed
echo "c=$c"

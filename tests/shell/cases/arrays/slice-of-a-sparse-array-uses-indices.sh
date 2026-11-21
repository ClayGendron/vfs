# tier: language
# world: none
a=([0]=a [5]=b [10]=c)
echo "1 -> ${a[@]:1}"
echo "3 -> ${a[@]:3}"
echo "6 -> ${a[@]:6}"

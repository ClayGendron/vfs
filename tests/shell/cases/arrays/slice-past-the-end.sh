# tier: language
# world: none
a=(a b c)
echo "1:10 -> [${a[@]:1:10}]"
echo "5 -> [${a[@]:5}]"
echo "2:0 -> [${a[@]:2:0}]"

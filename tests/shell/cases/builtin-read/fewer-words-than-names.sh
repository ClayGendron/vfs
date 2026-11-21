# tier: language
# world: none
read a b c <<< "only"
echo "a=[$a] b=[$b] c=[$c]"
echo "c is ${c+set}"

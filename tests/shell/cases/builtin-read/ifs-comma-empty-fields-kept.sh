# tier: language
# world: none
IFS=, read a b c <<< "x,,z"
echo "a=[$a] b=[$b] c=[$c]"
IFS=, read a b c <<< ",y,"
echo "a=[$a] b=[$b] c=[$c]"

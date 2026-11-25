# tier: language
# world: none
IFS=, read a b <<< "1,2,"
echo "a=[$a] b=[$b]"
IFS=, read a b <<< "1,2,,"
echo "a=[$a] b=[$b]"

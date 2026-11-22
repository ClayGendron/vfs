# tier: language
# world: none
IFS=' ,' read a b c <<< "a , b,c"
echo "a=[$a] b=[$b] c=[$c]"
IFS=' ,' read a b c <<< "a  ,  , c"
echo "a=[$a] b=[$b] c=[$c]"

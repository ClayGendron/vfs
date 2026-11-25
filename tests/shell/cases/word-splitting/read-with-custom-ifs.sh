# tier: language
# world: none
IFS=, read -r a b <<< 'x,y,z'
echo "a=[$a] b=[$b]"
IFS=, read -r a b c <<< 'x,,z'
echo "a=[$a] b=[$b] c=[$c]"

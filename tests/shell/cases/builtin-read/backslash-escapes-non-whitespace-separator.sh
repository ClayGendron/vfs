# tier: language
# world: none
IFS=, read a b <<< 'x\,y,z'
echo "a=[$a] b=[$b]"

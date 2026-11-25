# tier: language
# world: none
read a b <<< 'one\ two three'
echo "a=[$a] b=[$b]"
read -r a b <<< 'one\ two three'
echo "a=[$a] b=[$b]"

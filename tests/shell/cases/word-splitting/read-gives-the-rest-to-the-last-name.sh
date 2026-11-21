# tier: language
# world: none
read a b c <<< '1 2 3 4  5'
echo "a=[$a] b=[$b] c=[$c]"
read a b <<< 'only'
echo "a=[$a] b=[$b]"

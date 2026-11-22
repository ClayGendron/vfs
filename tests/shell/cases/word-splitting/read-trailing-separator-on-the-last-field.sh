# tier: language
# world: none
IFS=: read -r a b <<< 'x:y:'
echo "a=[$a] b=[$b]"
IFS=: read -r a b <<< 'x:y::'
echo "a=[$a] b=[$b]"
IFS=: read -r a <<< 'x:'
echo "a=[$a]"

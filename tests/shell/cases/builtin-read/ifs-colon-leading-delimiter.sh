# tier: language
# world: none
IFS=: read a b <<< ":x:y"
echo "a=[$a] b=[$b]"

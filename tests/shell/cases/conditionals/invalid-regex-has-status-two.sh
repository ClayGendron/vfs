# tier: language
# world: none
re='('
[[ abc =~ $re ]]
echo "unbalanced: status=$?"
re='a{2,1}'
[[ abc =~ $re ]]
echo "bad interval: status=$?"

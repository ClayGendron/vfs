# tier: language
# world: none
read -d : first <<< "alpha:beta"
echo "first=[$first]"
read -d , a b <<< "x y,z"
echo "a=[$a] b=[$b]"

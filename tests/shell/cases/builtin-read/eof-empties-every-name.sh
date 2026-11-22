# tier: language
# world: none
: > empty.txt
a=1 b=2
read a b < empty.txt
echo "status=$? a=[$a] b=[$b]"

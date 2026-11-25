# tier: language
# world: none
printf 'alpha beta\ngamma\n' > in.txt
read -r a b < in.txt
echo "a=[$a] b=[$b]"

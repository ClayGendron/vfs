# tier: language
# world: none
printf 'keep\n' > f
echo -n "K" 1<> f
read -r x < f
echo "x=$x"

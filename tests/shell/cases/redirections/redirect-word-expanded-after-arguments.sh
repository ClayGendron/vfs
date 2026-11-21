# tier: language
# world: none
i=0
echo "arg $((i += 1))" > "f$((i += 1))"
read -r x < f2
echo "f2=[$x] i=$i"

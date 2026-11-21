# tier: language
# world: none
a=(a b c d e)
echo "1:2 -> ${a[@]:1:2}"
echo "2 -> ${a[@]:2}"
echo "0:1 -> ${a[@]:0:1}"
printf '[%s]' "${a[@]:3}"; echo

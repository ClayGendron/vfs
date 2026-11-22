# tier: program
# world: seed
sed -n '1~2p' data/numbers.txt | tr '\n' ' '
echo
sed -n '0~3p' data/numbers.txt | tr '\n' ' '
echo

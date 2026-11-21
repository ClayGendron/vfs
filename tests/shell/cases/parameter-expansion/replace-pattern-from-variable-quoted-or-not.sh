# tier: language
# world: none
x='a*b*c'
p='*'
echo "[${x/"$p"/S}] [${x/$p/S}]"
echo "[${x//"$p"/S}]"

# tier: language
# world: none
x='a*b'
p='*'
echo "[${x#*"$p"}] [${x#*$p}]"

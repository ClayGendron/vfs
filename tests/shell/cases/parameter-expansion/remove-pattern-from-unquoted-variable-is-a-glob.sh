# tier: language
# world: none
x=aXbXc
p='a*'
echo "[${x#$p}] [${x##$p}] [${x#"$p"}]"

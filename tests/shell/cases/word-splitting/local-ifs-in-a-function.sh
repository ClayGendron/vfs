# tier: language
# world: none
v='a:b c'
f() { local IFS=:; printf '[%s]\n' $v; }
f
echo ---
printf '[%s]\n' $v

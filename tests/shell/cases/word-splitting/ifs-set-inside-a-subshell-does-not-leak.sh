# tier: language
# world: none
v='a:b'
( IFS=:; printf '[%s]\n' $v )
echo ---
printf '[%s]\n' $v

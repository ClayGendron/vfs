# tier: language
# world: none
IFS=' ,'
v=' , a'
printf '[%s]\n' $v
echo ---
v='a, ,b'
printf '[%s]\n' $v

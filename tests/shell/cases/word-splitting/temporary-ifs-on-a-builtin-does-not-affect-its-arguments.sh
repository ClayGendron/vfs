# tier: language
# world: none
v='a:b'
IFS=: printf '[%s]\n' $v
echo ---
IFS=: eval 'printf "[%s]\n" $v'

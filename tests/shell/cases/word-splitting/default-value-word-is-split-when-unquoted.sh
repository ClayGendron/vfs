# tier: language
# world: none
unset u
printf '[%s]\n' ${u:-a b}
echo ---
printf '[%s]\n' ${u:-'a b'}
echo ---
printf '[%s]\n' "${u:-a b}"

# tier: language
# world: none
v='a,b,c'
printf '[%s]\n' ${v//,/ }
set -- ${v//,/ }
echo "count=$#"

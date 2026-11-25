# tier: language
# world: none
IFS='é'
v='aébéc'
printf '[%s]\n' $v
set -- x y
echo "$*"

# tier: language
# world: none
printf '[%s]\n' $'\101\102' $'\1011' $'\60'
x=$'\7'
echo "len=${#x}"
[ "$x" = $'\a' ] && echo "\\7 is bell"

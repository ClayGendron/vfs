# tier: language
# world: none
printf '[%s]\n' $'\x41\x42' $'\x4a\x4A' $'\x411'
x=$'\x4'
echo "len=${#x}"
[ "$x" = $'\004' ] && echo "\\x4 is byte 4"

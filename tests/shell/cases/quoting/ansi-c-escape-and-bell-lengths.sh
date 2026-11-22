# tier: language
# world: none
x=$'\a\b\e\E\f\v\r'
echo "len=${#x}"
[ $'\e' = $'\033' ] && echo "e is 033"
[ $'\E' = $'\033' ] && echo "E is 033"

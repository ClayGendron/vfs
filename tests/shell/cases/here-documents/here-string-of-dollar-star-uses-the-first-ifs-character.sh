# tier: language
# world: none
set -- a b c
IFS=,
read -r line <<< "$*"
echo "line=[$line]"

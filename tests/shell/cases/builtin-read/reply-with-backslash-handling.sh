# tier: language
# world: none
read <<< 'a\ b\\c'
echo "REPLY=[$REPLY]"
read -r <<< 'a\ b\\c'
echo "REPLY=[$REPLY]"

# tier: language
# world: none
echo -e '\01014'
echo -e '\0060x'
echo -e '[\07]' | { IFS= read -r l; echo "len=${#l}"; }

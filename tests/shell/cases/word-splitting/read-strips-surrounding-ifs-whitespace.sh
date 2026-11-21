# tier: language
# world: none
read -r v <<< '   hi there   '
echo "[$v]"
IFS= read -r v <<< '   hi there   '
echo "[$v]"

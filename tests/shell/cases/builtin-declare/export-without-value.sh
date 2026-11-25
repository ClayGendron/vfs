# tier: language
# world: none
export E
declare -p E
echo "value=[${E-unset}]"
E=now
declare -p E

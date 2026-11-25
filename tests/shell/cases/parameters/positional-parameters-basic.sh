# tier: language
# world: none
set -- a b c
echo "1=$1 2=$2 3=$3 count=$#"
echo "4=[${4-unset}]"

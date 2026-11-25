# tier: language
# world: none
IFS=, read -r a b c <<< "1,2,3"
echo "a=$a b=$b c=$c"
IFS=: read -r -a fields <<< "x::y"
echo "fields=${#fields[@]} [${fields[1]}]"

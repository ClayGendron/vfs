# tier: language
# world: none
x=outer
read -r got < <(x=inner; echo "$x")
echo "got=[$got] x=[$x]"

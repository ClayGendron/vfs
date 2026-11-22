# tier: language
# world: none
printf '[%s]\n' $'é' $'\u41' $'café' $'\U0001F600'
x=$'é'
echo "chars=${#x}"

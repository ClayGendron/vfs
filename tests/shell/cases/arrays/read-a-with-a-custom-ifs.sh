# tier: language
# world: none
IFS=, read -r -a fields <<< "ada,36,,london"
echo "count=${#fields[@]}"
printf '[%s]\n' "${fields[@]}"

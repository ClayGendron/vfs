# tier: language
# world: none
v=$(echo -e 'a\0b')
echo "len=${#v}"
echo -e 'nul:\0:end' | { IFS= read -r -d '' first; echo "first=[$first]"; }

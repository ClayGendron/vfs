# tier: language
# world: none
printf 'a\0b' > out.bin
IFS= read -r -d '' first < out.bin
echo "first=[$first]"

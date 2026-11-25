# tier: language
# world: none
printf '%b' 'x\0y' > out.bin
IFS= read -r -d '' first < out.bin
echo "first=[$first]"

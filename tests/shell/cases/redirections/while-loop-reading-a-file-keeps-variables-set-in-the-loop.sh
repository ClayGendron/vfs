# tier: language
# world: none
printf 'a\nb\nc\n' > f
last=none
while read -r line; do last=$line; done < f
echo "last=$last"

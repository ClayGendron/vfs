# tier: language
# world: none
path=/a/b/file.txt
ref=path
echo "${!ref##*/} ${!ref^^}"

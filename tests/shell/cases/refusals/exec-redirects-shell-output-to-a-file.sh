# tier: language
# world: none
exec 3>&1
exec >log.txt
echo "into the file"
exec >&3 3>&-
echo "back on stdout"
while IFS= read -r l; do echo "log: $l"; done <log.txt

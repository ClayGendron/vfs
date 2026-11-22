# tier: language
# world: none
printf 'l1\nl2\nl3\n' > lines.txt
exec 3< lines.txt
read -r skipped <&3
mapfile -t -u 3 rest
exec 3<&-
echo "skipped=$skipped rest=${rest[*]}"

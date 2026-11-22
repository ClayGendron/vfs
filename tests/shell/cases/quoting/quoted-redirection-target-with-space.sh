# tier: language
# world: none
echo hi > 'out file'
read -r l < "out file"
echo "read back: $l"
f='out file'
echo again >> "$f"
while IFS= read -r l; do echo "[$l]"; done < "$f"

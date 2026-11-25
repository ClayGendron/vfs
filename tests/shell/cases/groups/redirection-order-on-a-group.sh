# tier: language
# world: none
{ echo out; echo err >&2; } 2>&1 > f.txt
IFS= read -r saved < f.txt
echo "file has: $saved"

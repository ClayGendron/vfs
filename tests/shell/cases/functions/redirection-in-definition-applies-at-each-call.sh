# tier: language
# world: none
f() { echo "call $1"; } > out.txt
f 1
f 2
while IFS= read -r line; do echo "file: $line"; done < out.txt

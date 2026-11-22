# tier: language
# world: none
while IFS= read -r l; do echo "out: $l"; done <<EOF > out.txt
one
EOF
IFS= read -r r < out.txt
echo "file: $r"

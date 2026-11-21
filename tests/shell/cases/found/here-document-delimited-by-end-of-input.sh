# tier: language
# world: none
while read -r l; do echo "h:$l"; done <<EOF
one
EOF; echo not-a-delimiter

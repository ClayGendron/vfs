# tier: language
# world: none
show() { while IFS= read -r l; do echo "show: $l"; done; }
show <<EOF
one
two
EOF

# tier: language
# world: none
v=val
while IFS= read -r line; do echo "$line"; done <<EOF
dollar: \$v
backtick: \`
backslash: \\
plain: $v
EOF

# tier: language
# world: none
x=value
while IFS= read -r l; do printf '%s\n' "$l"; done <<E"OF"
x is $x
EOF
while IFS= read -r l; do printf '%s\n' "$l"; done <<\END
y is $x
END

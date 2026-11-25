# tier: language
# world: none
IFS= read -r -d '' text <<EOF
ends with a backslash \\
EOF
printf '[%s]\n' "$text"

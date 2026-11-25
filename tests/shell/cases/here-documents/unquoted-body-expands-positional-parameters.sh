# tier: language
# world: none
set -- alpha beta gamma
while IFS= read -r line; do echo "$line"; done <<EOF
count=$# first=$1 all=$@
EOF

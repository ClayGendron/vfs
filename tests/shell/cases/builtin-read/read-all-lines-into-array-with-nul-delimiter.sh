# tier: language
# world: none
IFS=$'\n' read -r -d '' -a lines <<'EOF'
line one
line two

line four
EOF
echo "status=$? count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"

# tier: language
# world: none
name=world
while IFS= read -r line; do echo "$line"; done <<'EOF'
hello $name
$(echo not run) $((1+1)) `echo no`
EOF

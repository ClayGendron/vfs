# tier: language
# world: none
n=0
while read -r _; do n=$((n+1)); done <<'EOF'
a
b

c
EOF
echo "lines=$n"

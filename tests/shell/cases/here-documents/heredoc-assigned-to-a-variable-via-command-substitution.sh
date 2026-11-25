# tier: language
# world: none
text=$(while IFS= read -r l; do printf '%s\n' "$l"; done <<'EOF'
alpha
beta
EOF
)
echo "lines: ${text//$'\n'/|}"

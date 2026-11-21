# tier: language
# world: none
result=$(while IFS= read -r l; do echo "<$l>"; done <<EOF
x
y
EOF
)
echo "result=[${result//$'\n'/,}]"

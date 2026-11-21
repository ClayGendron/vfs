# tier: language
# world: none
while read -r a; do
  read -r b
  echo "$a+$b"
done <<'EOF'
1
2
3
4
EOF

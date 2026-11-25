# tier: language
# world: none
read a b c <<'EOF'
one \
two \
three four
EOF
echo "a=[$a] b=[$b] c=[$c]"

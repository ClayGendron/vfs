# tier: language
# world: none
read -r a <<< 'keep'
read x <<'EOF'
ab\
cd \
ef
EOF
echo "x=[$x] a=[$a]"

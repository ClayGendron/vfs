# tier: language
# world: none
read -r a <<EOF
   padded   
EOF
IFS= read -r b <<EOF
   padded   
EOF
echo "default=[$a] empty-ifs=[$b]"

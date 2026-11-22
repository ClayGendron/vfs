# tier: language
# world: none
read -r a b rest <<EOF
one two three four
EOF
echo "a=[$a] b=[$b] rest=[$rest]"

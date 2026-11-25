# tier: language
# world: none
{
  read -r a
  read -r b
  read -r c
} <<'EOF'
one
two
EOF
echo "status=$? a=[$a] b=[$b] c=[$c]"

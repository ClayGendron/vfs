# tier: language
# world: none
printf 'hello\nworld\n\n\n' > f
content=$(< f)
echo "[$content]"

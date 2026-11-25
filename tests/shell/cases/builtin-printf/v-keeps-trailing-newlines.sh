# tier: language
# world: none
printf -v x 'line\n\n'
echo "len=${#x}"
y=$(printf 'line\n\n')
echo "len=${#y}"

# tier: language
# world: none
unset IFS
read a b <<< $'  x \t y  '
echo "a=[$a] b=[$b]"

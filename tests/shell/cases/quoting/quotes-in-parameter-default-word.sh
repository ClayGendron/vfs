# tier: language
# world: none
unset u
echo "${u:-"a  b"}"
echo "${u:-'q'}"
echo ${u:-'q'}
printf '[%s]\n' ${u:-"x y"} ${u:-x y}

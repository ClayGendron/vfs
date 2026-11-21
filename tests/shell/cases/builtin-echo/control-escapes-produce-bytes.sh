# tier: language
# world: none
v=$(echo -e '\a\b\f\v\r')
echo "len=${#v}"
printf '%q\n' "$(echo -e 'x\ry')"
printf '%q\n' "$(echo -e '\e[0m')"
printf '%q\n' "$(echo -e '\E')"

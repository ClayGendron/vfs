# tier: language
# world: none
shopt -s extglob
x=000420
echo "${x##+(0)}"
echo "${x%%+(0)}"
y='  padded  '
echo "[${y##+([[:space:]])}]"

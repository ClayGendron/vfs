# tier: language
# world: none
f='file.tar.gz'
echo "${f%.*}" "${f%%.*}" "${f%'.*'}"
g='x.*'
echo "${g%'.*'}" "${g%.\*}"

# tier: language
# world: none
x='a*b'
echo "${x#"a*"}"
echo "${x#a*}"
echo "${x#'a*'}"
echo "${x#a\*}"

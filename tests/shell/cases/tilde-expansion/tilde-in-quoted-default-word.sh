# tier: language
# world: none
unset x
echo "${x:-~}" "${x:-~/y}"

# tier: language
# world: none
unset x
echo "${x:-temp}"
echo "after=[${x}] set=${x+yes}"

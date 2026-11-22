# tier: language
# world: none
unset target
ref=target
echo "${!ref:-fallback}"
target=set
echo "${!ref:-fallback}"

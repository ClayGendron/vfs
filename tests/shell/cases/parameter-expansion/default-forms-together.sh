# tier: language
# world: none
unset x
echo "${x:-fallback}"
x=""
echo "${x:-empty-counts}"
echo "${x-set-but-empty}|"
x=value
echo "${x:+alternate}"
echo "${#x}"

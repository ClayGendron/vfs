# tier: language
# world: none
pa=1
pb=2
IFS=,
printf '[%s]\n' "${!p@}"
printf '[%s]\n' "${!p*}"

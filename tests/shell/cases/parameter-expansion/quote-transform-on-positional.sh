# tier: language
# world: none
set -- one 'two words' ''
printf '<%s>\n' "${@@Q}"

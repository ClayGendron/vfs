# tier: language
# world: none
set -- a b
printf '[%s]\n' "${@:+yes}"
set --
printf '[%s]\n' "${@:+yes}"

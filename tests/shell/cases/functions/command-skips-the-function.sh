# tier: language
# world: none
printf() { builtin printf 'function printf\n'; }
printf '%s\n' direct
command printf '%s\n' "via command"
builtin printf '%s\n' "via builtin"

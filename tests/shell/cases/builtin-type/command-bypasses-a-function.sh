# tier: language
# world: none
printf() { builtin printf 'shadowed\n'; }
printf '%s\n' one
command printf '%s\n' two

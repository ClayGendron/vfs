# tier: language
# world: none
out=$(printf 'a\nb\n')
[[ $out == $'a\nb' ]]; echo "trailing newline stripped: $?"

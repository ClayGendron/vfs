# tier: language
# world: none
[[ abc =~ a.c ]] && echo "unquoted regex matches"
[[ abc =~ "a.c" ]] || echo "quoted regex is literal"
[[ a.c =~ "a.c" ]] && echo "literal dot matches"
re='^a.c$'
[[ abc =~ $re ]] && echo "regex in variable matches"

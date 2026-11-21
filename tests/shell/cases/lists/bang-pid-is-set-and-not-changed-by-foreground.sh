# tier: language
# world: none
true &
p=$!
wait
true | true
[ "$p" = "$!" ] && echo "\$! unchanged by a foreground pipeline"
[ -n "$p" ] && echo "\$! is set"

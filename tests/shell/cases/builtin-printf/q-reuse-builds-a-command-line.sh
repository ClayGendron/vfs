# tier: language
# world: none
set -- 'one two' "three's" four
printf -v cmd '%q ' "$@"
echo "cmd=[$cmd]"

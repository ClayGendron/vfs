# tier: language
# world: none
printf '[%s]\n' $(printf 'a\n\nb\n\n')
set -- $(printf 'one\ntwo three\n')
echo "count=$#"

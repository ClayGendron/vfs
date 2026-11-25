# tier: language
# world: seed
shopt -s nullglob
set -- *.nomatch
echo "count=$#"
printf '[%s]\n' docs/*.md *.zzz

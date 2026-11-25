# tier: language
# world: none
printf -v list '%s,' a b c
echo "list=[$list]"
echo "trimmed=[${list%,}]"

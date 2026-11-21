# tier: language
# world: none
a=("a b" "" c)
set -- ${a[@]}
echo "unquoted words=$#"
set -- "${a[@]}"
echo "quoted words=$#"
set -- "${a[*]}"
echo "star words=$#"

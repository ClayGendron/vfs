# tier: language
# world: none
a=('' x '')
set -- "${a[@]}"
echo "quoted count=$#"
set -- ${a[@]}
echo "unquoted count=$#"

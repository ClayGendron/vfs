# tier: language
# world: none
set -- a b
shopt -s shift_verbose
shift 3 2>&1
echo "status=$? count=$#"

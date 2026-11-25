# tier: language
# world: none
hello() { echo "hello $1"; }
cmd=hello
$cmd world
cmds=(hello there)
"${cmds[@]}"

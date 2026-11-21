# tier: language
# world: none
setvar() { local -n ref=$1; ref="set via nameref"; }
setvar target
echo "target=$target"

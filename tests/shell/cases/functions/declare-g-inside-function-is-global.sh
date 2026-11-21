# tier: language
# world: none
f() { declare -g made_here=yes; declare not_global=no; }
f
echo "made_here=[${made_here-unset}] not_global=[${not_global-unset}]"

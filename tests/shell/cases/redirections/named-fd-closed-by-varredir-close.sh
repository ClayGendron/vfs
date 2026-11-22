# tier: language
# world: none
shopt -s varredir_close
: {fd}> f
echo hi >&$fd
echo "status=$?"

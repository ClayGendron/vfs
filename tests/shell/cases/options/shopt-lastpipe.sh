# tier: language
# world: none
echo piped | read -r x
echo "default x=[$x]"
shopt -s lastpipe
echo piped | read -r x
echo "lastpipe x=[$x]"

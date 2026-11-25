# tier: language
# world: none
shopt -s lastpipe
set_it() { read -r value; }
value=original
echo piped | set_it
echo "value=$value"

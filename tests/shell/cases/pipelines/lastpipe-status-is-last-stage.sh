# tier: language
# world: none
shopt -s lastpipe
false | true
echo "false|true: $?"
true | false
echo "true|false: $?"

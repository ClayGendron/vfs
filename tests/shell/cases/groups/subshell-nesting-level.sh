# tier: language
# world: none
echo "level $BASH_SUBSHELL"
(echo "level $BASH_SUBSHELL"; (echo "level $BASH_SUBSHELL"))
x=$(echo "substitution level $BASH_SUBSHELL")
echo "$x"

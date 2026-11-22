# tier: language
# world: none
'if' true 2>/dev/null
echo "quoted if: $?"
\then 2>/dev/null
echo "escaped then: $?"
"ec"ho "quoted command name works"

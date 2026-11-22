# tier: language
# world: none
# stderr: exact
printf 'hello\n' >&-
echo "status=$?"

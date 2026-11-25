# tier: language
# world: none
# stderr: exact
printf -v '1bad' '%s' x
echo "status=$?"

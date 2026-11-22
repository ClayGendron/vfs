# tier: language
# world: none
# stderr: exact
printf '%d\n' 9223372036854775807
printf '%d\n' -9223372036854775808
printf '%d\n' 9223372036854775808
echo "status=$?"

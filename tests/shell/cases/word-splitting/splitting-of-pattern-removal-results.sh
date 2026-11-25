# tier: language
# world: none
v='key = value with spaces'
printf '[%s]\n' ${v#*= }
echo ---
printf '[%s]\n' "${v#*= }"

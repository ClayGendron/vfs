# tier: language
# world: none
read -r -a first <<'END'
one two
three four
END
echo "${first[*]}"

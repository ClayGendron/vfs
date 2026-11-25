# tier: language
# world: none
x=foo.bar
y=foo
echo "${x#${y}.}"
echo "${x#"$y".}"

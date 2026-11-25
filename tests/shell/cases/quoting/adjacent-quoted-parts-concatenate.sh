# tier: language
# world: none
echo 'a'"b"c$'d'
printf '[%s]\n' 'a b'"c d"e\ f
x=X
printf '[%s]\n' pre"$x"'$x'post

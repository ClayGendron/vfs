# tier: language
# world: none
printf '[%s]\n' {a,b} "{a,b}" '{a,b}' \{a,b\}
printf '[%s]\n' {"a b",c}
printf '[%s]\n' x{'1 2',3}

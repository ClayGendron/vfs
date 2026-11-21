# tier: language
# world: none
x=1
printf '[%s]\n' ${x:+"a b"}
unset x
printf '[%s]\n' ${x:+"a b"} end
set -- "one arg"
printf '[%s]\n' ${1:+"$1"}

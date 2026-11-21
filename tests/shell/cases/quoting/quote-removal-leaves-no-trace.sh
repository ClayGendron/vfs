# tier: language
# world: none
printf '[%s]\n' "abc" 'abc' a"b"c \a\b\c
[ "abc" = a'b'c ] && echo equal

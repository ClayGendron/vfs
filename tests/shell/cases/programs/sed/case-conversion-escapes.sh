# tier: program
# world: seed
echo 'hello world' | sed 's/\w\+/\u&/g'
echo 'hello world' | sed 's/.*/\U&/'
echo 'HELLO World' | sed -E 's/(\w+) (\w+)/\L\1\E \2/'

# tier: program
# world: seed
echo 'john smith' | sed -E 's/(.*) (.*)/\2, \1/'
echo 'aaa bbb' | sed -E 's/a+/X/'

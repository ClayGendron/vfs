# tier: language
# world: none
HOME=/home/agent
x=$(echo '$HOME ~ `echo no`')
echo "[$x]"
printf '[%s]\n' $(echo '$HOME')

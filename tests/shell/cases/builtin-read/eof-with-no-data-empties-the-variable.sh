# tier: language
# world: none
: > empty.txt
x=old
read x < empty.txt
echo "status=$? x=[$x] set=${x+yes}"

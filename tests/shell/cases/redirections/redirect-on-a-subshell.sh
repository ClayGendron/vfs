# tier: language
# world: none
( echo inner; x=changed ) > s.txt
read -r line < s.txt
echo "line=$line x=${x-unset}"

# tier: language
# world: none
IFS=$'\t' read a b c <<< $'one two\t\tthree'
echo "a=[$a] b=[$b] c=[$c]"

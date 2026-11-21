# tier: language
# world: none
IFS=, read name age city <<< "ada,36,london"
echo "name=$name age=$age city=$city"

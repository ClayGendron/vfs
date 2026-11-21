# tier: language
# world: none
echo first >f.txt
set -C
echo forced >|f.txt
echo "status=$?"
read -r line <f.txt
echo "file=$line"

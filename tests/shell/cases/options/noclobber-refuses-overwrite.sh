# tier: language
# world: none
echo first >f.txt
set -C
echo second >f.txt 2>/dev/null
echo "status=$?"
read -r line <f.txt
echo "file=$line"

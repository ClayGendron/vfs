# tier: language
# world: none
echo first >f.txt
set -o noclobber
{ echo second >f.txt; } 2>&1
echo "status=$?"

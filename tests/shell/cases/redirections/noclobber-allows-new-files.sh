# tier: language
# world: none
set -C
echo fresh > new.txt
echo "status=$?"
read -r x < new.txt
echo "x=$x"

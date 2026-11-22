# tier: language
# world: none
HOME=$PWD
echo tilde > ~/t.txt
read -r x < t.txt
echo "x=$x"

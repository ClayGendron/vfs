# tier: language
# world: none
set -f
x=file.txt
[[ $x == *.txt ]] && echo "bracket match"
case $x in *.txt) echo "case match" ;; esac
echo "${x%.*}"

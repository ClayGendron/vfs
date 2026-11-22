# tier: language
# world: none
# world: seed
shopt -s extglob
cd docs
echo !(*.md)
echo @(a|b).md
echo +([a-z]).txt

# tier: language
# world: none
x='abc 123 def'
echo "${x//[0-9]/(&)}"
echo "${x/[0-9]*/{&}}"

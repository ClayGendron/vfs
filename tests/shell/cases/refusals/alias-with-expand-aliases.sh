# tier: language
# world: none
shopt -s expand_aliases
alias greet='echo hello'
greet world
unalias greet
echo "unalias status=$?"

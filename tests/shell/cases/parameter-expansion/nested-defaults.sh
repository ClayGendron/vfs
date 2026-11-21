# tier: language
# world: none
unset a b
c=deep
echo "${a:-${b:-${c:-none}}}"
unset c
echo "${a:-${b:-${c:-none}}}"

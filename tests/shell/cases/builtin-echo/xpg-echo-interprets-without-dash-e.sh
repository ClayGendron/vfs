# tier: language
# world: none
shopt -s xpg_echo
echo 'a\tb'
echo -E 'c\td'
echo -e 'e\tf'
shopt -u xpg_echo
echo 'g\th'

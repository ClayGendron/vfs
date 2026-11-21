# tier: language
# world: none
a=(apple banana cherry)
echo "${a[@]/a/A}"
echo "${a[@]//a/A}"
echo "${a[@]/an}"

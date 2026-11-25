# tier: program
# world: seed
echo 'Abc 123 x_y' | sed 's/[[:digit:]]/#/g'
echo 'Abc 123 x_y' | sed 's/[[:upper:]]/U/g'
echo 'Abc 123 x_y' | sed 's/[^a-z ]//g'

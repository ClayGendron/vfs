# tier: program
# world: seed
echo 'bracket:'
find . -name '[ab].md' | sort
echo 'question:'
find . -name '????.txt' | sort
echo 'digits:'
touch data/v2.txt
find data -name '*[0-9]*'
echo "status=$?"

# tier: program
# world: seed
n=$(grep -c . data/words.txt)
u=$(sort -u data/words.txt | wc -l)
echo "lines=$n unique=$u"

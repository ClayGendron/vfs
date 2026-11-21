# tier: program
# world: seed
cp data/people.csv p.csv
sed -i '1d;/boston/d' p.csv
cat p.csv

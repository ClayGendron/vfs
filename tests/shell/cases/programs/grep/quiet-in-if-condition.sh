# tier: program
# world: seed
if grep -q apple data/words.txt; then echo "has apple"; fi
if ! grep -q kiwi data/words.txt; then echo "no kiwi"; fi

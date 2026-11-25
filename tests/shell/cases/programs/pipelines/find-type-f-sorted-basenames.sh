# tier: program
# world: seed
find . -type f -name '*.*' | sed 's|.*/||' | sort | head -n 5

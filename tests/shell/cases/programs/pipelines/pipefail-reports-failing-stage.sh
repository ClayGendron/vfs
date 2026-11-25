# tier: program
# world: seed
set -o pipefail
grep zebra docs/notes.txt | sort
echo "status=$?"

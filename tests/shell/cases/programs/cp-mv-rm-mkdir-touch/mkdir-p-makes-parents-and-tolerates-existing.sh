# tier: program
# world: seed
mkdir -p a/b/c
echo "status=$?"
mkdir -p a/b/c docs
echo "status=$?"
find a | sort

# tier: language
# world: seed
cd src && echo "in src"
cd missing 2>/dev/null || echo "fallback: $?"
cd lib && pwd

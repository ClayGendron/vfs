# tier: language
# world: none
i=0
while ((i < 2)); do ((i++)); false; done
echo "status=$?"

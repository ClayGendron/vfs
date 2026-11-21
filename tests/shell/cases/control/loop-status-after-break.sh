# tier: language
# world: none
for i in 1; do false; break; done
echo "break status=$?"
for i in; do false; done
echo "empty loop status=$?"
while false; do :; done
echo "while status=$?"

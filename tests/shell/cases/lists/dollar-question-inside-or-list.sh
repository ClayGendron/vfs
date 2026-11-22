# tier: language
# world: none
false || echo "left status was $?"
(exit 4) || echo "left status was $?"
true && echo "left status was $?"

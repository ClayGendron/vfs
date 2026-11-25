# tier: language
# world: none
x='*ab*'
echo "[${x#"*"}] [${x#\*}] [${x#*}]"
echo "[${x%"*"}] [${x%\*}]"

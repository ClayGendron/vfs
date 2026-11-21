# tier: language
# world: none
read -r x <<< "from here-string" <<EOF
from heredoc
EOF
echo "x=$x"

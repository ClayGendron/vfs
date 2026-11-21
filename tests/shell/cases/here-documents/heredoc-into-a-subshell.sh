# tier: language
# world: none
( read -r a; echo "inside: $a" ) <<EOF
from heredoc
EOF
echo "outside: ${a-unset}"

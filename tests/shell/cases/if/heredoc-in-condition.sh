# tier: language
# world: none
if read -r l <<EOF
from heredoc
EOF
then echo "l=[$l]"
fi

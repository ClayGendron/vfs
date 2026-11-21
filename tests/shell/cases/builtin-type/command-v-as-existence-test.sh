# tier: language
# world: none
if command -v printf >/dev/null; then echo "printf available"; fi
if ! command -v nosuch_command_name >/dev/null; then echo "nosuch missing"; fi

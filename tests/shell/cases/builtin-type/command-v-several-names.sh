# tier: language
# world: none
f() { :; }
command -v f nosuch_command_name echo
echo "status=$?"

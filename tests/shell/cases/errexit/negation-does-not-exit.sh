# tier: language
# world: none
set -e
! true
echo "after ! true status=$?"
! false
echo "after ! false status=$?"

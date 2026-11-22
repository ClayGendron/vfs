# tier: language
# world: none
! false && echo x &
wait
! true || echo y &
wait
true && ! true &
wait $!
echo "status=$?"
{ ! false; echo "inner=$?"; } &
wait

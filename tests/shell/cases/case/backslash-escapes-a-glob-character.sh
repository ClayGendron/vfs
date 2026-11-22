# tier: language
# world: none
case 'a?' in a\?) echo "literal question mark" ;; esac
case ab in a\?) echo "never" ;; *) echo "ab does not match a\\?" ;; esac

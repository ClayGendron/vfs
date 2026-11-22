# tier: language
# world: none
shopt -s extglob
str=x; [[ $str == !($str) ]]; echo "neg=$?"
prefix=pre; [[ --pre-long-option == --@(help|verbose|$prefix-@(long|short)-'option') ]]; echo "nested=$?"
v=b; case abc in a@($v)c) echo arm;; *) echo none;; esac

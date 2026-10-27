# Command x source matrix

Sources: bb=busybox (390), tb=toybox (198), uu=uutils (108), sb=sbase (96), p9p=plan9port (151), 9f=9front (425), jb=just-bash (90), bk=bashkit-all (193), jbp=just-bash-py (69), lf=lifo (81), am=amla-sandbox (13).
Corpus: 67446 pipeline segments (e2/commands.md, head-word table).

| command | corpus n | share | agent peers (of 5) | unix (of 6) | class | ships in |
|---|---:|---:|---:|---:|---|---|
| `grep` | 14094 | 20.90% | 5 | 5 | a | bb tb sb p9p 9f jb bk jbp lf am |
| `head` | 10644 | 15.78% | 5 | 4 | b | bb tb uu sb jb bk jbp lf am |
| `echo` | 9038 | 13.40% | 4 | 6 | c | bb tb uu sb p9p 9f jb bk jbp am |
| `sed` | 8180 | 12.13% | 4 | 5 | b | bb tb sb p9p 9f jb bk jbp lf |
| `cd` | 6277 | 9.31% | 1 | 0 | c | bk |
| `uv` | 3636 | 5.39% | 0 | 0 | f |  |
| `tail` | 2747 | 4.07% | 5 | 6 | b | bb tb uu sb p9p 9f jb bk jbp lf am |
| `cat` | 2609 | 3.87% | 5 | 6 | a | bb tb uu sb p9p 9f jb bk jbp lf am |
| `ls` | 2097 | 3.11% | 5 | 5 | a | bb tb uu p9p 9f jb bk jbp lf am |
| `git` | 1892 | 2.81% | 1 | 1 | f | 9f bk |
| `python3` | 667 | 0.99% | 1 | 0 | e | jb |
| `wc` | 626 | 0.93% | 5 | 6 | b | bb tb uu sb p9p 9f jb bk jbp lf am |
| `cut` | 462 | 0.68% | 5 | 4 | b | bb tb uu sb jb bk jbp lf am |
| `rg` | 393 | 0.58% | 3 | 0 | a | jb bk jbp |
| `awk` | 331 | 0.49% | 3 | 3 | b | bb p9p 9f jb jbp lf |
| `find` | 282 | 0.42% | 3 | 3 | a | bb tb sb jb jbp lf |
| `sleep` | 250 | 0.37% | 4 | 6 | c | bb tb uu sb p9p 9f jb bk jbp lf |
| `mkdir` | 248 | 0.37% | 4 | 6 | a | bb tb uu sb p9p 9f jb bk jbp lf |
| `sort` | 230 | 0.34% | 5 | 6 | b | bb tb uu sb p9p 9f jb bk jbp lf am |
| `unset` | 195 | 0.29% | 1 | 0 | c | bk |
| `cp` | 187 | 0.28% | 4 | 5 | a | bb tb uu sb 9f jb bk jbp lf |
| `printf` | 175 | 0.26% | 3 | 4 | c | bb tb uu sb jb jbp lf |
| `docker` | 162 | 0.24% | 0 | 0 | f |  |
| `nl` | 141 | 0.21% | 4 | 4 | b | bb tb uu sb jb bk jbp lf |
| `perl` | 110 | 0.16% | 0 | 0 | e |  |
| `tr` | 103 | 0.15% | 5 | 5 | b | bb uu sb p9p 9f jb bk jbp lf am |
| `uniq` | 86 | 0.13% | 5 | 6 | b | bb tb uu sb p9p 9f jb bk jbp lf am |
| `curl` | 84 | 0.12% | 4 | 0 | f | jb bk jbp lf |
| `ps` | 84 | 0.12% | 2 | 2 | f | tb 9f bk lf |
| `rm` | 79 | 0.12% | 4 | 6 | a | bb tb uu sb p9p 9f jb bk jbp lf |
| `source` | 73 | 0.11% | 0 | 0 | c |  |
| `gh` | 61 | 0.09% | 0 | 0 | f |  |
| `break` | 50 | 0.07% | 1 | 0 | c | bk |
| `pkill` | 44 | 0.07% | 1 | 1 | f | bb bk |
| `run` | 44 | 0.07% | 0 | 0 | ? |  |
| `tee` | 43 | 0.06% | 4 | 6 | b | bb tb uu sb p9p 9f jb bk jbp lf |
| `show` | 43 | 0.06% | 0 | 0 | ? |  |
| `export` | 35 | 0.05% | 1 | 0 | c | bk |
| `time` | 34 | 0.05% | 2 | 5 | c | bb tb sb p9p 9f jb jbp |
| `pgrep` | 29 | 0.04% | 1 | 1 | f | bb bk |
| `diff` | 27 | 0.04% | 4 | 3 | b | bb p9p 9f jb bk jbp lf |
| `date` | 22 | 0.03% | 4 | 6 | c | bb tb uu sb p9p 9f jb bk jbp lf |
| `.` | 22 | 0.03% | 1 | 0 | c | bk |
| `cargo` | 22 | 0.03% | 0 | 0 | f |  |
| `pdftotext` | 21 | 0.03% | 0 | 0 | f |  |
| `uptime` | 19 | 0.03% | 1 | 4 | f | bb tb uu 9f lf |
| `du` | 16 | 0.02% | 4 | 6 | a | bb tb uu sb p9p 9f jb bk jbp lf |
| `chmod` | 14 | 0.02% | 4 | 5 | f | bb tb uu sb 9f jb bk jbp lf |
| `pmset` | 14 | 0.02% | 0 | 0 | f |  |
| `mv` | 13 | 0.02% | 4 | 4 | a | bb uu sb 9f jb bk jbp lf |
| `sysctl` | 12 | 0.02% | 0 | 2 | f | bb tb |
| `which` | 11 | 0.02% | 4 | 3 | c | bb tb sb jb bk jbp lf |
| `wait` | 10 | 0.01% | 1 | 0 | c | bk |
| `base64` | 9 | 0.01% | 4 | 3 | b | bb tb uu jb bk jbp lf |
| `true` | 9 | 0.01% | 3 | 4 | c | bb tb uu sb jb bk jbp |
| `python` | 8 | 0.01% | 1 | 0 | e | jb |
| `file` | 7 | 0.01% | 4 | 3 | a | tb p9p 9f jb bk jbp lf |
| `fold` | 7 | 0.01% | 3 | 4 | b | bb tb uu sb jb bk jbp |
| `vfs` | 7 | 0.01% | 0 | 0 | f |  |
| `paste` | 6 | 0.01% | 3 | 4 | b | bb tb uu sb jb bk jbp |
| `set` | 6 | 0.01% | 1 | 0 | c | bk |
| `symbolic-ref` | 6 | 0.01% | 0 | 0 | ? |  |
| `kill` | 5 | 0.01% | 2 | 4 | c | tb uu sb 9f bk lf |
| `tar` | 4 | 0.01% | 4 | 5 | b | bb tb sb p9p 9f jb bk jbp lf |
| `bash` | 4 | 0.01% | 2 | 1 | e | bb jb jbp |
| `md_probe` | 4 | 0.01% | 0 | 0 | ? |  |
| `open` | 4 | 0.01% | 0 | 0 | f |  |
| `psql` | 4 | 0.01% | 0 | 0 | f |  |
| `stat` | 3 | 0.00% | 4 | 3 | a | bb tb uu jb bk jbp lf |
| `test` | 3 | 0.00% | 1 | 6 | c | bb tb uu sb p9p 9f bk |
| `nproc` | 3 | 0.00% | 1 | 2 | f | bb uu bk |
| `continue` | 3 | 0.00% | 1 | 0 | c | bk |
| `shift` | 3 | 0.00% | 1 | 0 | c | bk |
| `tokei` | 3 | 0.00% | 0 | 0 | f |  |
| `exit` | 2 | 0.00% | 1 | 0 | c | bk |
| `hash-object` | 2 | 0.00% | 0 | 0 | ? |  |
| `odbcinst` | 2 | 0.00% | 0 | 0 | f |  |
| `basename` |  |  | 4 | 6 | c | bb tb uu sb p9p 9f jb bk jbp lf |
| `seq` |  |  | 4 | 6 | b | bb tb uu sb p9p 9f jb bk jbp lf |
| `strings` |  |  | 4 | 5 | b | bb tb sb p9p 9f jb bk jbp lf |
| `dirname` |  |  | 4 | 4 | c | bb tb uu sb jb bk jbp lf |
| `env` |  |  | 4 | 4 | c | bb tb uu sb jb bk jbp lf |
| `ln` |  |  | 4 | 4 | a | bb tb uu sb jb bk jbp lf |
| `rmdir` |  |  | 4 | 4 | a | bb tb uu sb jb bk jbp lf |
| `xargs` |  |  | 4 | 4 | b | bb tb sb 9f jb bk jbp lf |
| `rev` |  |  | 4 | 3 | b | bb tb sb jb bk jbp lf |
| `tac` |  |  | 4 | 3 | b | bb tb uu jb bk jbp lf |
| `help` |  |  | 4 | 1 | c | tb jb bk jbp lf |
| `tree` |  |  | 4 | 1 | a | bb jb bk jbp lf |
| `jq` |  |  | 4 | 0 | b | jb bk jbp am |
| `comm` |  |  | 3 | 6 | b | bb tb uu sb p9p 9f jb bk jbp |
| `split` |  |  | 3 | 6 | b | bb tb uu sb p9p 9f jb bk jbp |
| `touch` |  |  | 3 | 6 | a | bb tb uu sb p9p 9f jb jbp lf |
| `pwd` |  |  | 3 | 5 | c | bb tb uu sb 9f jb bk jbp |
| `expand` |  |  | 3 | 4 | b | bb tb uu sb jb bk jbp |
| `gzip` |  |  | 3 | 4 | b | bb tb p9p 9f jb bk lf |
| `join` |  |  | 3 | 4 | b | uu sb p9p 9f jb bk jbp |
| `mktemp` |  |  | 3 | 4 | ? | bb tb uu sb jb bk lf |
| `od` |  |  | 3 | 4 | b | bb tb uu sb jb bk jbp |
| `readlink` |  |  | 3 | 4 | a | bb tb uu sb jb bk jbp |
| `yes` |  |  | 3 | 4 | b | bb tb uu sb jb bk lf |
| `expr` |  |  | 3 | 3 | c | bb uu sb jb bk jbp |
| `hostname` |  |  | 3 | 3 | f | tb uu sb jb jbp lf |
| `sha256sum` |  |  | 3 | 3 | b | bb uu sb jb bk lf |
| `timeout` |  |  | 3 | 3 | c | bb tb uu jb bk jbp |
| `whoami` |  |  | 3 | 3 | f | bb uu sb jb jbp lf |
| `gunzip` |  |  | 3 | 1 | b | bb jb bk lf |
| `column` |  |  | 3 | 0 | b | jb bk jbp |
| `yq` |  |  | 3 | 0 | b | jb bk jbp |
| `md5sum` |  |  | 2 | 6 | b | bb tb uu sb p9p 9f jb bk |
| `sha1sum` |  |  | 2 | 5 | b | bb uu sb p9p 9f jb bk |
| `false` |  |  | 2 | 4 | c | bb tb uu sb jb bk |
| `printenv` |  |  | 2 | 4 | c | bb tb uu sb jb bk |
| `chown` |  |  | 2 | 3 | f | bb uu sb bk lf |
| `df` |  |  | 2 | 3 | a | bb tb uu bk lf |
| `shuf` |  |  | 2 | 3 | b | bb tb uu bk jbp |
| `unexpand` |  |  | 2 | 3 | b | bb uu sb jb bk |
| `clear` |  |  | 2 | 2 | ? | bb tb jb bk |
| `free` |  |  | 2 | 2 | f | bb tb bk lf |
| `read` |  |  | 2 | 2 | c | p9p 9f bk jbp |
| `realpath` |  |  | 2 | 2 | a | bb uu bk lf |
| `watch` |  |  | 2 | 2 | ? | bb tb bk lf |
| `wget` |  |  | 2 | 2 | f | bb tb bk lf |
| `egrep` |  |  | 2 | 1 | ? | bb jb bk |
| `fgrep` |  |  | 2 | 1 | ? | bb jb bk |
| `history` |  |  | 2 | 1 | c | 9f jb bk |
| `unzip` |  |  | 2 | 1 | b | bb bk lf |
| `alias` |  |  | 2 | 0 | c | jb bk |
| `node` |  |  | 2 | 0 | e | jb lf |
| `sqlite3` |  |  | 2 | 0 | e | jb jbp |
| `unalias` |  |  | 2 | 0 | c | jb bk |
| `xan` |  |  | 2 | 0 | b | jb jbp |
| `zip` |  |  | 2 | 0 | b | bk lf |
| `dd` |  |  | 1 | 6 | ? | bb tb uu sb p9p 9f bk |
| `chgrp` |  |  | 1 | 5 | f | bb tb uu sb 9f bk |
| `cmp` |  |  | 1 | 5 | b | bb tb sb p9p 9f bk |
| `factor` |  |  | 1 | 5 | ? | bb tb uu p9p 9f bk |
| `cksum` |  |  | 1 | 4 | b | bb tb uu sb bk |
| `fmt` |  |  | 1 | 4 | b | tb uu p9p 9f bk |
| `link` |  |  | 1 | 4 | ? | bb tb uu sb bk |
| `mkfifo` |  |  | 1 | 4 | ? | bb tb uu sb bk |
| `nice` |  |  | 1 | 4 | ? | bb tb uu sb bk |
| `nohup` |  |  | 1 | 4 | ? | bb tb uu sb bk |
| `sum` |  |  | 1 | 4 | b | bb uu p9p 9f bk |
| `sync` |  |  | 1 | 4 | ? | bb tb uu sb bk |
| `tsort` |  |  | 1 | 4 | b | bb tb uu sb bk |
| `tty` |  |  | 1 | 4 | f | bb tb uu sb bk |
| `uname` |  |  | 1 | 4 | f | bb tb uu sb lf |
| `unlink` |  |  | 1 | 4 | ? | bb tb uu sb bk |
| `bc` |  |  | 1 | 3 | ? | bb p9p 9f bk |
| `bzip2` |  |  | 1 | 3 | ? | bb p9p 9f bk |
| `flock` |  |  | 1 | 3 | ? | bb tb sb bk |
| `install` |  |  | 1 | 3 | ? | bb uu sb bk |
| `netstat` |  |  | 1 | 3 | f | bb tb 9f lf |
| `patch` |  |  | 1 | 3 | ? | bb tb 9f bk |
| `pr` |  |  | 1 | 3 | b | uu p9p 9f bk |
| `sha512sum` |  |  | 1 | 3 | b | bb uu sb bk |
| `truncate` |  |  | 1 | 3 | ? | bb tb uu bk |
| `who` |  |  | 1 | 3 | f | tb uu 9f bk |
| `arch` |  |  | 1 | 2 | ? | bb uu bk |
| `base32` |  |  | 1 | 2 | b | bb uu bk |
| `bzcat` |  |  | 1 | 2 | ? | bb tb bk |
| `getconf` |  |  | 1 | 2 | ? | tb sb bk |
| `hostid` |  |  | 1 | 2 | ? | bb uu bk |
| `iconv` |  |  | 1 | 2 | ? | tb 9f bk |
| `ifconfig` |  |  | 1 | 2 | f | bb tb lf |
| `ip` |  |  | 1 | 2 | f | p9p 9f lf |
| `man` |  |  | 1 | 2 | ? | bb 9f bk |
| `more` |  |  | 1 | 2 | ? | bb uu bk |
| `ping` |  |  | 1 | 2 | f | bb tb lf |
| `sha224sum` |  |  | 1 | 2 | ? | uu sb bk |
| `users` |  |  | 1 | 2 | f | bb uu bk |
| `vi` |  |  | 1 | 2 | ? | bb 9f bk |
| `xxd` |  |  | 1 | 2 | b | bb tb bk |
| `b2sum` |  |  | 1 | 1 | ? | uu bk |
| `basenc` |  |  | 1 | 1 | ? | uu bk |
| `bunzip2` |  |  | 1 | 1 | ? | bb bk |
| `hexdump` |  |  | 1 | 1 | b | bb bk |
| `host` |  |  | 1 | 1 | f | tb lf |
| `less` |  |  | 1 | 1 | ? | bb bk |
| `log` |  |  | 1 | 1 | ? | tb bk |
| `numfmt` |  |  | 1 | 1 | b | uu bk |
| `route` |  |  | 1 | 1 | f | bb lf |
| `sh` |  |  | 1 | 1 | e | 9f jb |
| `sha384sum` |  |  | 1 | 1 | ? | uu bk |
| `ssh` |  |  | 1 | 1 | f | 9f bk |
| `top` |  |  | 1 | 1 | f | bb lf |
| `ulimit` |  |  | 1 | 1 | c | tb bk |
| `uuidgen` |  |  | 1 | 1 | ? | tb bk |
| `zcat` |  |  | 1 | 1 | b | bb jb |
| `:` |  |  | 1 | 0 | ? | bk |
| `assert` |  |  | 1 | 0 | ? | bk |
| `bg` |  |  | 1 | 0 | c | bk |
| `busybox` |  |  | 1 | 0 | ? | bk |
| `caller` |  |  | 1 | 0 | c | bk |
| `compgen` |  |  | 1 | 0 | c | bk |
| `csv` |  |  | 1 | 0 | ? | bk |
| `dig` |  |  | 1 | 0 | f | lf |
| `dirs` |  |  | 1 | 0 | c | bk |
| `disown` |  |  | 1 | 0 | c | bk |
| `dotenv` |  |  | 1 | 0 | ? | bk |
| `enable` |  |  | 1 | 0 | c | bk |
| `envsubst` |  |  | 1 | 0 | ? | bk |
| `eval` |  |  | 1 | 0 | c | bk |
| `fc` |  |  | 1 | 0 | c | bk |
| `fg` |  |  | 1 | 0 | c | bk |
| `forward` |  |  | 1 | 0 | ? | lf |
| `glob` |  |  | 1 | 0 | ? | bk |
| `hash` |  |  | 1 | 0 | c | bk |
| `html-to-markdown` |  |  | 1 | 0 | ? | jb |
| `http` |  |  | 1 | 0 | ? | bk |
| `jobs` |  |  | 1 | 0 | c | bk |
| `js-exec` |  |  | 1 | 0 | e | jb |
| `json` |  |  | 1 | 0 | ? | bk |
| `lifo` |  |  | 1 | 0 | ? | lf |
| `local` |  |  | 1 | 0 | c | bk |
| `locale` |  |  | 1 | 0 | ? | bk |
| `logout` |  |  | 1 | 0 | c | lf |
| `make` |  |  | 1 | 0 | f | bk |
| `mapfile` |  |  | 1 | 0 | c | bk |
| `nano` |  |  | 1 | 0 | ? | bk |
| `newtab` |  |  | 1 | 0 | ? | lf |
| `npm` |  |  | 1 | 0 | f | lf |
| `openssl` |  |  | 1 | 0 | ? | bk |
| `parallel` |  |  | 1 | 0 | ? | bk |
| `pkg` |  |  | 1 | 0 | ? | lf |
| `popd` |  |  | 1 | 0 | c | bk |
| `ports` |  |  | 1 | 0 | ? | lf |
| `pushd` |  |  | 1 | 0 | c | bk |
| `readarray` |  |  | 1 | 0 | c | bk |
| `readonly` |  |  | 1 | 0 | c | bk |
| `retry` |  |  | 1 | 0 | ? | bk |
| `return` |  |  | 1 | 0 | c | bk |
| `scp` |  |  | 1 | 0 | f | bk |
| `semver` |  |  | 1 | 0 | ? | bk |
| `sftp` |  |  | 1 | 0 | f | bk |
| `shasum` |  |  | 1 | 0 | ? | bk |
| `shopt` |  |  | 1 | 0 | c | bk |
| `sl` |  |  | 1 | 0 | ? | lf |
| `sudo` |  |  | 1 | 0 | f | bk |
| `systemctl` |  |  | 1 | 0 | f | lf |
| `template` |  |  | 1 | 0 | ? | bk |
| `times` |  |  | 1 | 0 | c | bk |
| `tomlq` |  |  | 1 | 0 | ? | bk |
| `tool` |  |  | 1 | 0 | ? | am |
| `trap` |  |  | 1 | 0 | c | bk |
| `type` |  |  | 1 | 0 | c | bk |
| `umask` |  |  | 1 | 0 | c | bk |
| `verify` |  |  | 1 | 0 | ? | bk |

vfs first call on a fresh process (opens the database): 15.2 ms

## Session replay: the 39 stages the session ran

| # | stage | lines | generic ms | rg ms | vfs ms | vfs first ms | agree |
|---|---|---|---|---|---|---|---|
| 0 | `grep -n '^struct inode {\\|^struct inode_operations {\\|^struct fil...` | 6 | 6.7 | 7.7 | 28.6 | 45.8 | yes |
| 0 | `grep -n '^struct dentry {' include/linux/dcache.h` | 1 | 3.9 | 6.4 | 17.5 | 21.4 | yes |
| 0 | `grep -n '^static int do_sys_openat2\\|^long do_sys_open\\|^ssize_t ...` | 3 | 5.3 | 9.1 | 16.4 | 23.4 | yes |
| 0 | `grep -n '^struct file \*path_openat\\|^static struct file \*path_op...` | 2 | 7.8 | 7.7 | 15.2 | 18.3 | yes |
| 0 | `grep -n '^const struct file_operations ext4_file_operations\\|^cons...` | 2 | 5.5 | 7.0 | 12.6 | 16.0 | yes |
| 1 | `sed -n 554,600p fs/read_write.c \| grep -n 'f_op\\|->read'` | 4 | 6.7 | 9.1 | 3.1 | 5.9 | yes |
| 1 | `sed -n 767,800p include/linux/fs.h` | 34 | 4.5 | 4.4 | 3.0 | 5.4 | yes |
| 2 | `grep -n '^struct address_space {\\|^struct address_space_operations...` | 2 | 5.2 | 6.1 | 18.4 | 21.9 | yes |
| 2 | `grep -n '^struct files_struct {\\|^struct fdtable {' include/linux/...` | 2 | 4.1 | 5.8 | 15.8 | 20.4 | yes |
| 2 | `grep -n '^struct mount {' fs/mount.h` | 1 | 4.0 | 6.1 | 12.6 | 15.0 | yes |
| 2 | `grep -n '^struct vfsmount {' include/linux/mount.h` | 1 | 4.1 | 5.3 | 15.1 | 17.3 | yes |
| 2 | `grep -n '^struct path {' include/linux/path.h` | 1 | 4.5 | 6.6 | 16.5 | 20.7 | yes |
| 2 | `grep -n '^struct file_system_type {' include/linux/fs.h 'include/li...` | 1 | 5.3 | 9.1 | 22.9 | 27.7 | yes |
| 2 | `grep -n '^struct nameidata {' fs/namei.c` | 1 | 4.6 | 5.5 | 10.7 | 14.1 | yes |
| 2 | `grep -n '^static int lookup_fast\\|^static struct dentry \*lookup_f...` | 6 | 9.2 | 6.8 | 16.9 | 20.1 | yes |
| 3 | `grep -n '^struct dentry \*__d_lookup_rcu\\|^struct dentry \*__d_loo...` | 7 | 5.9 | 6.9 | 13.8 | 17.8 | yes |
| 3 | `grep -n '^void iput(\\|^static void evict(\\|^struct inode \*iget_l...` | 6 | 5.4 | 6.3 | 15.2 | 17.3 | yes |
| 3 | `grep -n '^ssize_t filemap_read(\\|^struct folio \*__filemap_get_fol...` | 5 | 7.2 | 7.7 | 12.5 | 18.6 | yes |
| 3 | `grep -n '^void writeback_inodes_sb(\\|^static void wb_workfn\\|^voi...` | 3 | 4.9 | 7.4 | 13.3 | 17.0 | yes |
| 4 | `grep -n '^int alloc_fd\\|^static int alloc_fd\\|^void fd_install(\\...` | 5 | 4.4 | 6.0 | 13.7 | 17.2 | yes |
| 4 | `grep -n '^int register_filesystem(\\|^struct dentry \*mount_bdev\\|...` | 4 | 5.0 | 9.1 | 15.9 | 20.2 | yes |
| 4 | `grep -n '^static int do_new_mount(\\|^static int path_mount(\\|^int...` | 7 | 8.1 | 9.2 | 15.7 | 20.9 | yes |
| 4 | `grep -n '^struct mnt_namespace {' fs/mount.h` | 1 | 3.9 | 6.0 | 11.8 | 16.6 | yes |
| 4 | `grep -n '^static int ext4_init_fs\\|^static struct file_system_type...` | 4 | 8.8 | 7.6 | 10.7 | 17.4 | yes |
| 4 | `ls fs/ramfs/` | 5 | 4.0 | 4.2 | 3.2 | 6.2 | yes |
| 4 | `ls Documentation/filesystems/ \| grep -E 'path-lookup\|vfs\|locking...` | 7 | 7.4 | 8.4 | 3.7 | 6.2 | yes |
| 5 | `sed -n 26,60p include/linux/fdtable.h` | 35 | 5.0 | 4.3 | 2.7 | 5.1 | yes |
| 5 | `sed -n 45,75p fs/mount.h` | 31 | 3.9 | 3.8 | 4.5 | 5.2 | yes |
| 5 | `sed -n 473,490p include/linux/fs.h` | 18 | 5.5 | 5.0 | 3.0 | 5.1 | yes |
| 5 | `sed -n 1838,1870p fs/namei.c` | 33 | 5.0 | 4.6 | 3.1 | 5.4 | yes |
| 5 | `sed -n 1916,1990p fs/inode.c \| grep -n 'i_nlink\\|drop_inode\\|evi...` | 8 | 7.0 | 10.0 | 3.9 | 5.9 | yes |
| 5 | `grep -n 'f_ref\\|f_count' include/linux/fs.h \| head -5` | 4 | 7.2 | 6.6 | 18.1 | 22.0 | yes |
| 5 | `grep -n i_count include/linux/fs.h \| head -3` | 3 | 5.8 | 6.1 | 15.7 | 19.2 | yes |
| 6 | `sed -n 1888,1925p fs/namei.c \| grep -n 'i_op->lookup\\|d_alloc_par...` | 2 | 6.0 | 7.8 | 3.0 | 5.1 | yes |
| 6 | `grep -n '__follow_mount_rcu\\|^static bool __follow_mount_rcu\\|^st...` | 4 | 12.4 | 8.7 | 14.3 | 18.7 | yes |
| 6 | `grep -n 'ramfs_get_inode\\|ramfs_fs_type\\|ramfs_dir_inode_operatio...` | 17 | 5.6 | 7.1 | 8.7 | 12.3 | yes |
| 6 | `grep -n '\.read_iter\\|\.write_iter\\|\.mmap' fs/ramfs/file-mmu.c` | 3 | 4.2 | 5.6 | 8.2 | 11.3 | yes |
| 6 | `grep -n '^struct dentry \*simple_lookup' fs/libfs.c` | 1 | 4.7 | 6.2 | 10.6 | 15.4 | yes |
| 6 | `sed -n 1260,1300p include/linux/fs.h \| grep -n 'f_pos\\|f_inode\\|...` | 7 | 6.4 | 8.3 | 2.8 | 5.1 | yes |

| stage kind | count | generic ms | rg ms | vfs ms |
|---|---|---|---|---|
| grep | 28 | 163.8 | 195.5 | 417.4 |
| sed | 9 | 50.0 | 57.2 | 29.1 |
| ls | 2 | 11.4 | 12.6 | 6.9 |
| **all** | 39 | 225.2 | 265.3 | 453.4 |

## Repo-wide grep: each session pattern over the whole tree

| pattern | hits gen/rg/vfs | files | generic ms | rg ms | vfs ms | vfs first ms | vfs notes |
|---|---|---|---|---|---|---|---|
| `^struct inode {\\|^struct inode_operations {\\|^struct fi...` | 11/11/11 | 6 | 37803 | 2882 | 343 | 395 |  |
| `^struct dentry {` | 1/1/1 | 1 | 11525 | 2932 | 84 | 105 |  |
| `^static int do_sys_openat2\\|^long do_sys_open\\|^ssize_t...` | 6/6/6 | 4 | 21715 | 2776 | 103 | 142 |  |
| `^struct file \*path_openat\\|^static struct file \*path_o...` | 2/2/2 | 1 | 21443 | 2851 | 82 | 99 |  |
| `^const struct file_operations ext4_file_operations\\|^con...` | 2/2/2 | 1 | 22532 | 2892 | 53 | 76 |  |
| `^struct address_space {\\|^struct address_space_operations {` | 3/3/3 | 2 | 17988 | 3052 | 159 | 187 |  |
| `^struct files_struct {\\|^struct fdtable {` | 2/2/2 | 1 | 16953 | 3012 | 91 | 116 |  |
| `^struct mount {` | 1/1/1 | 1 | 11580 | 2887 | 70 | 95 |  |
| `^struct vfsmount {` | 1/1/1 | 1 | 11966 | 2948 | 49 | 67 |  |
| `^struct path {` | 1/1/1 | 1 | 11717 | 3101 | 57 | 74 |  |
| `^struct file_system_type {` | 1/1/1 | 1 | 12222 | 2952 | 126 | 158 |  |
| `^struct nameidata {` | 1/1/1 | 1 | 12030 | 2993 | 46 | 68 |  |
| `^static int lookup_fast\\|^static struct dentry \*lookup_...` | 7/7/7 | 2 | 38758 | 3354 | 147 | 227 |  |
| `^struct dentry \*__d_lookup_rcu\\|^struct dentry \*__d_lo...` | 7/7/7 | 1 | 34631 | 3324 | 83 | 103 |  |
| `^void iput(\\|^static void evict(\\|^struct inode \*iget_...` | 7/7/7 | 2 | 28027 | 3157 | 105 | 131 |  |
| `^ssize_t filemap_read(\\|^struct folio \*__filemap_get_fo...` | 10/10/10 | 5 | 32491 | 2936 | 142 | 167 |  |
| `^void writeback_inodes_sb(\\|^static void wb_workfn\\|^vo...` | 5/5/5 | 3 | 22421 | 3255 | 69 | 85 |  |
| `^int alloc_fd\\|^static int alloc_fd\\|^void fd_install(\...` | 5/5/5 | 1 | 26822 | 3240 | 109 | 131 |  |
| `^int register_filesystem(\\|^struct dentry \*mount_bdev\\...` | 5/5/5 | 3 | 26770 | 3182 | 78 | 97 |  |
| `^static int do_new_mount(\\|^static int path_mount(\\|^in...` | 8/8/8 | 3 | 39131 | 2160 | 83 | 121 |  |
| `^struct mnt_namespace {` | 1/1/1 | 1 | 13992 | 2695 | 52 | 71 |  |
| `^static int ext4_init_fs\\|^static struct file_system_typ...` | 4/4/4 | 1 | 30648 | 3107 | 64 | 79 |  |
| `f_ref\\|f_count` | 4581/4581/4581 | 1011 | 30934 | 3141 | 296 | 357 |  |
| `i_count` | 769/769/769 | 221 | 17375 | 3017 | 194 | 214 |  |
| `__follow_mount_rcu\\|^static bool __follow_mount_rcu\\|^s...` | 5/5/5 | 3 | 36324 | 3054 | 70 | 87 |  |
| `ramfs_get_inode\\|ramfs_fs_type\\|ramfs_dir_inode_operati...` | 46/46/46 | 20 | 68154 | 3105 | 123 | 181 |  |
| `\.read_iter\\|\.write_iter\\|\.mmap` | 1088/1088/1088 | 619 | 37137 | 3083 | 122 | 172 |  |
| `^struct dentry \*simple_lookup` | 1/1/1 | 1 | 12982 | 2854 | 62 | 178 |  |
| **total** | | | 706070 | 83940 | 3060 | | |

## Repo-wide glob

| case | count gen/rg/vfs | generic ms | rg ms | vfs ms |
|---|---|---|---|---|
| names matching *{path-lookup,vfs,locking,porting,mount_api}* | 102/102/102 | 538 | 107 | 47 |
| every header, **/*.h | 26702/26702/26702 | 458 | 106 | 377 |

## Crossover: in hand vs index, measured on SQLite and projected to a remote database

| scope | files | MB | pattern | local SQLite: index / in hand ms | same region: 1 ms RTT, 1 Gbit/s: index / in hand ms | cross region: 20 ms RTT, 1 Gbit/s: index / in hand ms |
|---|---|---|---|---|---|---|
| mm/tests | 1 | 0.0 | rare | 11 / 8 **hand** | 30 / 23 **hand** | 391 / 308 **hand** |
| mm/tests | 1 | 0.0 | medium | 10 / 9 **hand** | 29 / 24 **hand** | 390 / 309 **hand** |
| mm/tests | 1 | 0.0 | common | 11 / 8 **hand** | 30 / 23 **hand** | 391 / 308 **hand** |
| mm/tests | 1 | 0.0 | very common | 14 / 8 **hand** | 33 / 23 **hand** | 394 / 308 **hand** |
| kernel/unwind | 3 | 0.0 | rare | 14 / 8 **hand** | 33 / 23 **hand** | 394 / 308 **hand** |
| kernel/unwind | 3 | 0.0 | medium | 13 / 7 **hand** | 33 / 22 **hand** | 413 / 307 **hand** |
| kernel/unwind | 3 | 0.0 | common | 13 / 8 **hand** | 32 / 23 **hand** | 393 / 308 **hand** |
| kernel/unwind | 3 | 0.0 | very common | 20 / 7 **hand** | 40 / 22 **hand** | 420 / 307 **hand** |
| kernel/kcsan | 10 | 0.2 | rare | 12 / 9 **hand** | 31 / 25 **hand** | 392 / 310 **hand** |
| kernel/kcsan | 10 | 0.2 | medium | 12 / 9 **hand** | 31 / 25 **hand** | 392 / 310 **hand** |
| kernel/kcsan | 10 | 0.2 | common | 14 / 9 **hand** | 33 / 25 **hand** | 394 / 310 **hand** |
| kernel/kcsan | 10 | 0.2 | very common | 21 / 9 **hand** | 41 / 25 **hand** | 421 / 310 **hand** |
| drivers/atm | 30 | 0.9 | rare | 54 / 9 **hand** | 74 / 31 **hand** | 454 / 316 **hand** |
| drivers/atm | 30 | 0.9 | medium | 77 / 9 **hand** | 97 / 31 **hand** | 477 / 316 **hand** |
| drivers/atm | 30 | 0.9 | common | 65 / 9 **hand** | 84 / 31 **hand** | 445 / 316 **hand** |
| drivers/atm | 30 | 0.9 | very common | 176 / 9 **hand** | 196 / 32 **hand** | 576 / 317 **hand** |
| drivers/clocksource | 100 | 0.8 | rare | 53 / 12 **hand** | 72 / 34 **hand** | 433 / 319 **hand** |
| drivers/clocksource | 100 | 0.8 | medium | 79 / 12 **hand** | 99 / 34 **hand** | 479 / 319 **hand** |
| drivers/clocksource | 100 | 0.8 | common | 64 / 12 **hand** | 84 / 33 **hand** | 464 / 318 **hand** |
| drivers/clocksource | 100 | 0.8 | very common | 174 / 13 **hand** | 194 / 34 **hand** | 574 / 319 **hand** |
| drivers/md | 296 | 5.9 | rare | 54 / 24 **hand** | 74 / 86 **index** | 454 / 371 **hand** |
| drivers/md | 296 | 5.9 | medium | 77 / 23 **hand** | 97 / 85 **hand** | 477 / 370 **hand** |
| drivers/md | 296 | 5.9 | common | 64 / 24 **hand** | 84 / 86 **index** | 464 / 371 **hand** |
| drivers/md | 296 | 5.9 | very common | 176 / 26 **hand** | 196 / 88 **hand** | 576 / 373 **hand** |
| drivers/gpu/drm/amd/display/dc | 1033 | 17.7 | rare | 19 / 101 **index** | 39 / 258 **index** | 419 / 543 **index** |
| drivers/gpu/drm/amd/display/dc | 1033 | 17.7 | medium | 20 / 98 **index** | 40 / 255 **index** | 420 / 540 **index** |
| drivers/gpu/drm/amd/display/dc | 1033 | 17.7 | common | 20 / 101 **index** | 40 / 258 **index** | 420 / 543 **index** |
| drivers/gpu/drm/amd/display/dc | 1033 | 17.7 | very common | 23 / 113 **index** | 43 / 270 **index** | 423 / 555 **index** |
| drivers/media | 3023 | 43.5 | rare | 62 / 213 **index** | 82 / 576 **index** | 462 / 861 **index** |
| drivers/media | 3023 | 43.5 | medium | 89 / 194 **index** | 109 / 558 **index** | 489 / 843 **index** |
| drivers/media | 3023 | 43.5 | common | 81 / 196 **index** | 101 / 559 **index** | 481 / 844 **index** |
| drivers/media | 3023 | 43.5 | very common | 270 / 262 **hand** | 291 / 625 **index** | 690 / 910 **index** |
| drivers/gpu | 8036 | 596.5 | rare | 118 / 848 **index** | 150 / 5635 **index** | 758 / 5920 **index** |
| drivers/gpu | 8036 | 596.5 | medium | 157 / 825 **index** | 193 / 5611 **index** | 877 / 5896 **index** |
| drivers/gpu | 8036 | 596.5 | common | 126 / 850 **index** | 158 / 5637 **index** | 766 / 5922 **index** |
| drivers/gpu | 8036 | 596.5 | very common | 371 / 954 **index** | 405 / 5741 **index** | 1051 / 6026 **index** |
| drivers | 37340 | 1102.6 | rare | 85 / 3729 **index** | 115 / 12566 **index** | 685 / 12889 **index** |
| drivers | 37340 | 1102.6 | medium | 191 / 3629 **index** | 230 / 12466 **index** | 971 / 12789 **index** |
| drivers | 37340 | 1102.6 | common | 172 / 3748 **index** | 204 / 12586 **index** | 812 / 12909 **index** |
| drivers | 37340 | 1102.6 | very common | 1531 / 4901 **index** | 1573 / 13738 **index** | 2371 / 14061 **index** |
| (whole tree) | 93759 | 1587.0 | rare | 88 / 9201 **index** | 114 / 21913 **index** | 608 / 22217 **index** |
| (whole tree) | 93759 | 1587.0 | medium | 194 / 9304 **index** | 230 / 22016 **index** | 914 / 22320 **index** |
| (whole tree) | 93759 | 1587.0 | common | 459 / 9454 **index** | 488 / 22166 **index** | 1039 / 22470 **index** |
| (whole tree) | 93759 | 1587.0 | very common | 1826 / 11003 **index** | 1854 / 23715 **index** | 2386 / 24019 **index** |

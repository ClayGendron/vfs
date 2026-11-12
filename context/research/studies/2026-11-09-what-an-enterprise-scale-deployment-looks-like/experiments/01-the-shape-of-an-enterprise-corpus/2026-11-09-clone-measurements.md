# Measured shape of seven source trees in the sibling clones, and the figures derived from the published studies

Every number here is EXECUTED on 2026-11-09 against the read-only sibling clones under `/Users/claygendron/Git/Repos/`, using `git ls-files` for the file list (so untracked build output is excluded and the tree is the one the project commits), `git ls-tree -r -l HEAD` for blob sizes, and `awk` for the directory, depth and percentile arithmetic. Depth is the number of directory components in the tracked path, so a file at the repository root has depth 0. A directory is counted if any tracked file lies under it. Percentiles are positional on the sorted list.

## Clones and commits

| Clone | Commit | Commit date |
|---|---|---|
| linux | faeab166167f5787719eb8683661fd41a3bb1514 | 2026-04-18 |
| freebsd-src | d9e2caccfac14c43bf9ad62bdd35d4a03356ff91 | 2026-10-02 |
| gitlabhq | c4bbe29d81d8fddd9dfe90a9fa57ce218e898157 | 2026-07-08 |
| go | dcc06a82727b447270b1a58cc5f86b49736e317c | 2026-11-07 |
| cpython | a497a11c46c2bf096dd544e7a422cc457e806916 | 2026-11-08 |
| postgres | 0607aa61090ac1b574f8bafe854c684195b31e16 | 2026-11-06 |
| sqlite | 3d17c3f9e95321b4630ddd21e1b0a314b3812f0a | 2026-08-04 |

## Files, directories and depth

| Clone | Tracked files | Directories | Files per directory | Mean depth | Max depth | Files at depth 0–1 | Files at depth 6 or more |
|---|---|---|---|---|---|---|---|
| linux | 93,878 | 6,161 | 15.2 | 3.81 | 10 | 1,187 | 9,413 (10.0%) |
| freebsd-src | 114,621 | 9,857 | 11.6 | 4.50 | 11 | 221 | 32,510 (28.4%) |
| gitlabhq | 70,236 | 13,040 | 5.4 | 3.78 | 10 | 491 | 8,255 (11.8%) |
| go | 16,190 | 1,837 | 8.8 | 3.85 | 13 | 445 | 2,700 (16.7%) |
| cpython | 5,985 | 522 | 11.5 | 2.54 | 10 | 838 | 105 (1.8%) |
| postgres | 7,726 | 712 | 10.9 | 3.53 | 6 | 53 | 47 (0.6%) |
| sqlite | 2,218 | 54 | 41.1 | 1.51 | 7 | 1,603 | 59 (2.7%) |

Direct children per directory, counting only directories that hold at least one tracked file: linux 5,805 such directories, mean 16.2, median 6, 90th percentile 33, largest 1,533; freebsd-src 9,423 such directories, mean 12.2, median 3, 90th percentile 24, largest 1,085. The median is far below the mean in both, the shape Douceur and Bolosky fitted with an offset inverse-square law in 1999.

## Blob sizes in bytes

| Clone | Files | Mean | Median | p90 | p99 | Largest | Total MiB |
|---|---|---|---|---|---|---|---|
| linux | 93,878 | 16,909 | 3,825 | 29,011 | 129,209 | 23,949,786 | 1,514 |
| freebsd-src | 114,621 | 13,420 | 2,676 | 20,830 | 139,293 | 49,378,520 | 1,467 |
| gitlabhq | 70,236 | 7,867 | 1,309 | 9,003 | 52,162 | 15,081,874 | 527 |
| cpython | 5,985 | 21,725 | 4,326 | 48,884 | 254,342 | 4,289,021 | 124 |

The go clone's size pass failed: the clone is partial, `git ls-tree -l` reached for blobs it does not hold locally, and the network fetch was refused (`unable to access 'https://github.com/golang/go/'`), so go has no size row; its file and directory counts above come from the first pass, which needs only the index.

## Commands

The file and directory pass: `git -C $r ls-files | awk -F/ 'NF>1{p=""; for(i=1;i<NF;i++){p=p (i>1?"/":"") $i; print p}}' | sort -u | wc -l` for directories, and `git -C $r ls-files | awk -F/ '{d=NF-1; s+=d; if(d>m)m=d; c[d]++} END{print s/NR, m; for(k in c) print k, c[k]}'` for depth.

The size pass: `git -C $r ls-tree -r -l HEAD | awk '$4!="-"{print $4}' | sort -n | awk '{a[NR]=$1; s+=$1} END{print NR, s/NR, a[int(NR/2)], a[int(NR*0.9)], a[int(NR*0.99)], a[NR], s/1048576}'`.

## Figures derived from the published studies (INFERRED arithmetic on READ numbers)

| Derived figure | Arithmetic | Result |
|---|---|---|
| Files per Windows desktop file system, 1998 (Douceur and Bolosky) | 140,647,042 files / 10,568 file systems | 13,300 |
| Mean file size, 1998 (Douceur and Bolosky Table 1) | 11,055,804 MB / 140,647,042 files | 78.6 KB |
| Files per directory, 2004 (Agrawal et al. means) | 90,000 / 8,900 | 10.1 |
| Files per directory, 2009 (Meyer and Bolosky means) | 225,000 / 36,000 | 6.25 (the paper's own figure) |
| File-count growth per year, 2000 to 2004 (Agrawal) | (90,000 / 30,000)^(1/4) | 32% |
| File-count growth per year, 2004 to 2009 (Agrawal to Meyer) | (225,000 / 90,000)^(1/5) | 20% |
| Directory-count growth per year, 2004 to 2009 | (36,000 / 8,900)^(1/5) | 32% |
| Mean file size growth per year, 2004 to 2009 | (318 / 189)^(1/5) | 11% |
| Files per organization, Varonis 2019 mean | 53,885,498,652 / 785 | 68.6 million |
| Folders per organization, Varonis 2019 mean | 4,332,290,346 / 785 | 5.52 million |
| Files per folder, Varonis 2019 | 53,885,498,652 / 4,332,290,346 | 12.4 |
| Terabytes per organization, Varonis 2019 | 54.58 PB / 785 | 69.5 TB (the report says 70) |
| Mean file size on corporate shares, Varonis 2019 | 1 TB / 1,460,000 files | 685 KB (decimal TB) to 753 KB (binary TiB) |
| Accounts per organization, Varonis 2019 | 12,754,608 / 785 | 16,250 |
| Files per account, Varonis 2019 | 53,885,498,652 / 12,754,608 | 4,225 |
| Folders per account, Varonis 2019 | 4,332,290,346 / 12,754,608 | 340 |
| Files per organization, Varonis 2017 mean | 2,800,000,000 / 80 | 35 million |
| Folders per organization, Varonis 2017 mean | 236,500,000 / 80 | 2.96 million |
| Files per TB, Varonis 2017 | 2,800,000,000 / 3.79 PB | 739,000 |
| Files in the median 2017 organization (6 TB) | 6 TB × 739,000 to 6 TB × 1,460,000 | 4.4 to 8.8 million |
| Accounts a 10-million-file corpus corresponds to at the 2019 rate | 10,000,000 / 4,225 | 2,370 |
| Directories a 10-million-file corpus holds at the measured ratios | 10,000,000 / 12.4, / 10.1, / 6.25 | 0.81, 0.99, 1.6 million |
| Bytes a 10-million-file corpus holds at the measured means | 10,000,000 × 318 KB, × 0.7 MB | 3.2 TB, 7 TB |
| Content items per Dropbox registered user, 2018 S-1 | 400 billion / 500 million | 800 |
| Mean bytes per Dropbox content item, 2018 S-1 | 1 EB / 400 billion | 2.5 MB |
| New Microsoft 365 documents per monthly active user per workday, 2025 | 3 billion / 400 million | 7.5 |
| Microsoft 365 storage pool, 1,000 and 10,000 licences | 1 TB + 10 GB × N | 11 TB and 101 TB |
| Files those pools hold if full at the Varonis 2019 density | 11 TB × 1.46 M, 101 TB × 1.46 M | 16 million and 147 million |

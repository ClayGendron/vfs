## mariadb probe — N=10,000, ordinary caller (88 pieces), unionall shape; warm = median of 3

Load 5s.

| knobs | statement | cold / warm / recall |
|---|---|---|
| mariadb_force=False, plus_zero=False | entries | 827 / 745 / exact |
| mariadb_force=False, plus_zero=False | scoped | 2.5 / 2.5 / exact |
| mariadb_force=False, plus_zero=False | count | 706 / 787 / exact |
| mariadb_force=False, plus_zero=False | top10 | 641 / 809 / exact |
| mariadb_force=False, plus_zero=True | entries | 92.3 / 85.1 / exact |
| mariadb_force=False, plus_zero=True | scoped | 8.9 / 4.5 / exact |
| mariadb_force=False, plus_zero=True | count | 57.0 / 51.3 / exact |
| mariadb_force=False, plus_zero=True | top10 | 14.1 / 14.8 / exact |
| mariadb_force=True, plus_zero=False | entries | 90.0 / 50.4 / exact |
| mariadb_force=True, plus_zero=False | scoped | 2.5 / 2.1 / exact |
| mariadb_force=True, plus_zero=False | count | 52.0 / 62.9 / exact |
| mariadb_force=True, plus_zero=False | top10 | 20.2 / 19.5 / exact |

**mariadb_force=False, plus_zero=False / entries**

```
PRIMARY e type=range key=ts_33d9f6c4_e_lvlpath rows=40208 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_33d9f6c4_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_33d9f6c4_e_lvlpath rows=229610 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_33d9f6c4_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**mariadb_force=False, plus_zero=False / count**

```
PRIMARY c type=index key=ts_33d9f6c4_c_entry rows=219852 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_33d9f6c4_e_lvlpath rows=40208 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_33d9f6c4_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=index key=ts_33d9f6c4_e_lvlpath rows=229610 Using where; Using index; Using join buffer (flat, BNL join)
UNION e type=ref key=ts_33d9f6c4_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**mariadb_force=False, plus_zero=True / entries**

```
PRIMARY e type=range key=ts_33d9f6c4_e_lvlpath rows=40208 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_33d9f6c4_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_33d9f6c4_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**mariadb_force=False, plus_zero=True / count**

```
PRIMARY c type=index key=ts_33d9f6c4_c_entry rows=219852 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_33d9f6c4_e_lvlpath rows=40208 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_33d9f6c4_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_33d9f6c4_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```

**mariadb_force=True, plus_zero=False / entries**

```
PRIMARY e type=range key=ts_33d9f6c4_e_lvlpath rows=40208 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_33d9f6c4_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_33d9f6c4_e_owner rows=24 Using index condition; Using where
UNION RESULT <union1,2,3,4> type=ALL key=None rows=None
```

**mariadb_force=True, plus_zero=False / count**

```
PRIMARY c type=index key=ts_33d9f6c4_c_entry rows=219852 Using index
PRIMARY <derived2> type=eq_ref key=distinct_key rows=1
DERIVED e type=range key=ts_33d9f6c4_e_lvlpath rows=40208 Using where; Using index
UNION ap type=ALL key=None rows=40 Table function: json_table
UNION e type=eq_ref key=ts_33d9f6c4_e_path rows=1 Using index condition; Using where
UNION ar type=ALL key=None rows=40 Table function: json_table
UNION e type=ALL key=None rows=229610 Range checked for each record (index map: 0x2)
UNION e type=ref key=ts_33d9f6c4_e_owner rows=24 Using index condition; Using where
UNION RESULT <union2,3,4,5> type=ALL key=None rows=None
```


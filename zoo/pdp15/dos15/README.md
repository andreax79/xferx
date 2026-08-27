DOS-15
======

Login as administrator

```
>MICLOG SYS
```

List files

```
$PIP

DOSPIP V6A

>L TT _ DK

     06-JAN-79
 DIRECTORY LISTING  (SCR)
   6133 FREE BLKS
      0 USER FILES
      0 USER BLKS
```

List files of UIC TMP

```
>L TT _ DK <TMP>

     06-JAN-79
 DIRECTORY LISTING  (TMP)
   6133 FREE BLKS
      2 USER FILES
     35 USER BLKS
 LPA    SRC      31  13-FEB-73
 LPA    BIN       4  13-FEB-73
```

List file with RIB data of UIC TMP

```
>L TT _ DK <TMP> (P)

     06-JAN-79
 DIRECTORY LISTING  (TMP)
   6133 FREE BLKS
      2 USER FILES
     35 USER BLKS
 LPA    SRC    1414(2)    31  13-FEB-73   1476    210
 LPA    BIN    1453(2)     4  13-FEB-73   1461    366
```


List Master File Directory

```
>L TT _ DK (M)

     06-JAN-79
 MFD DIRECTORY LISTING
   6133 FREE BLKS
     53 USER FILES
    735 USER BLKS
 BNK     54(1)      5   161
 PAG    302(1)      5   161
 IOS    277(1)     31   310
 SCR    NON(0)      0     0
 PER    NON(1)      0     0
 REN     53(1)      6    26
 TMP   1403(0)      2    35
```

List SYSBLK directory

```
>L TT _ DK (L)


 SYSBLK LISTING

  NAME      FB    NB    FA    PS    SA
 RESMON      0    40   100 17400     0
 .SYSLD     40    13 11000  5100 11000
 ^QAREA    762   200     5 77773     0
 EDIT      317    15 11135  6007 11404
 EDITVP    334    17 10121  6755 10402
 EDITVT    353    17 10130  6773 10406
 PIP       372    33  2435 15202  2573
 QFILE     427     2 17041   437 17045
 MACRO     431    33  2530 15106  2530
 CREF      464     5 15600  1772 15601
 CHAIN     471    21  7240 10377  7240
 F4        512    35  2005 15632  2132
 DUMP      547     5 15300  2337 15300
 DTCOPY    554     3 16662   755 16701
 PATCH     557    10 12700  3465 12700
 UPDATE    567    13 12370  5247 12371
 SRCCOM    602    13 12646  4771 12751
 8TRAN     615    11 13607  4030 13671
 89TRAN    626    11 13562  4055 13644
 MTDUMP    637    12 13167  4450 13260
 SGEN      651    22  5510 10413  5553
 TKB       706    21  7573 10044  7750
 DOS15     727    33   516 15362  1075
```

Display a file

```
>T TT _ DK <TMP> LPA;SRC


        .TITLE  LPA.15   EDIT 42
/COPYRIGHT 1971, DIGITAL EQUIPMENT CORP., MAYNARD, MASS.
/9-23-71        EDIT 42
/J.M. WOLFBERG
/LPA.--IOPS LINE PRINTER HANDLER FOR LP15 LINE PRINTER
/       INTERFACE FOR DATA PRODUCTS 2310 AND 2410 LINE
...
```

Create a new UFD `ABC`

```
>N DK <ABC>
```

References
----------

* [DOS-15 Users Manual](https://bitsavers.org/pdf/dec/pdp15/DEC-15-ODUMA-A_DOS-15_Users_Manual_197212.pdf)
* [DOS-15 System Manual](https://bitsavers.org/pdf/dec/pdp15/DEC-15-ODFFA-A_DOS15_SysMan.pdf)
* [PDP-15 Utility Programs](https://bitsavers.org/pdf/dec/pdp15/DEC-15-YWZA-D_PDP-15_Utility_Programs_196910.pdf)
* [PIP DOS Monitor Utility Program](https://bitsavers.org/pdf/dec/pdp15/DEC-15-UPIPA-A-D_PIP_DOS_Monitor_Utility_Program_197408.pdf)
* [PDP-15 System Software Handouts](https://bitsavers.org/pdf/dec/pdp15/PDP-15_System_Software_Handouts_1975.pdf)

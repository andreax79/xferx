OS/8
====

Directory
---------

```
.DIR DEV:LISTFILE.DI<DEV:FILETYPE
.DIR FILETYPE

*	Wild name or extension
?	Wild character

/B	Include starting block numbers (octal)
/C	List only files with current date
/E	Include empties
/F	Fast mode
/I	Print additional info words
/L	Usual mode
/M	List empties only
/O	List only files with other than today's date
/R	List remainder of files after first one (but use /c,/o)
/U	Treat each input specification separately
/V	List files not of form specified
/W	Give version number
=N	Use n columns
```

Example: 
```
.DIR



SYS  VOLUME--   1
SYS:=RX8E
OS/8 SYSTEM   VERSION   3Q

BUILD .SV  33           HELP  .SV   8           BASIC .UF   4
ABSLDR.SV   5           PAL8  .SV  19           BCOMP .SV  17
BITMAP.SV   5           PIP   .SV  11           BLOAD .SV   8
BOOT  .SV   5           PT8E  .BN   1           BRTS  .SV  15
CCL   .SV  18           RESORC.SV  10           EABRTS.BN  24
CREF  .SV  13           RXCOPY.SV   6           RESEQ .BA   6
DIRECT.SV   7           SABR  .SV  24           ECHO  .SV   2
EDIT  .SV  10           TECO  .SV  22           RKLFMT.SV   9
EPIC  .SV  14           BASIC .AF   4           SET   .SV  14
FBOOT .SV   2           BASIC .FF   4           BATCH .SV  10
FOTP  .SV   8           BASIC .SF   4           FUTIL .SV  26
HELP  .HL  55           BASIC .SV   9           IDS   .SV   5

  36 FILES IN  437 BLOCKS -    1 FREE BLOCKS
```

References
----------

* [OS/8 Software Support Manual](https://www.bitsavers.org/pdf/dec/pdp8/os8/DEC-S8-OSSMB-A-D_OS8_v3ssup.pdf)

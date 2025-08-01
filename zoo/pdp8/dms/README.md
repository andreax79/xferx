4k Disk Monitor System
======================

Filenames are limited to four characters in
length and can be composed of any combination of alphanumeric
characters or special characters with the following exceptions.

- Imbedded spaces cannot appear in a filename
- A file name cannot be one of the following words or symbols: CALL SAVE ! , ; :

Extensions to the filenames specified by the user are automatically
appended by the system.
They are used internally by the system and cannot be referred to or modified.
The extensions are:
- SYS (n) Saved system program file in core bank n.
- USER (n) Saved user program file in core bank n.
- ASCII Source language program file (input to PAL-D Assembler or
- FORTRAN Compiler).
- BINARY Binary program file (output from PAL-D Assembler).
- FTC BIN Interpretive binary file (output from FORTRAN Compiler).

List files
----------

```
.PIP
*OPT-L    << L (press, L, without enter)

*IN-S:    << S: (device name, S: + enter)

FB=0047

NAME  TYPE    BLK

AF
PIP .SYS (0) 0025
EDIT.SYS (0) 0016
LOAD.SYS (0) 0011
.CD..SYS (0) 0007
PALD.SYS (0) 0037
DDT .SYS (0) 0002
.DDT.USER(0) 0022
.SYM.USER(0) 0022
FORT.SYS (0) 0010
.FT..SYS (0) 0035
.OS..SYS (0) 0025
FOSL.SYS (0) 0010
STBL.SYS (0) 0001
DIAG.SYS (0) 0004
STAT.ASCII   0003
PUNR.ASCII   0004
```

Devices:
* S: System device
* D0-D7: DECtape unit

Show file
---------

```
.PIP
*OPT-A      << A "Copy ASCII" (press, A, without enter)

*OUT-T:     << T: "to terminal"
*           << Press CTRL/P
*IN-S:STAT
*C      CALCULATE STATISTICS ON DATA FROM LOW SPEED READER
        SUM=0
        SUMSQ=0
        TYPE 100
100     FORMAT("ENTER THE NUMBER OF VALUES TO CACULATE STATISTICS ON",/)
        ACCEPT 10,N
10      FORMAT(I)
        DO 200 I=1,N
        READ 1,110,V
110     FORMAT(E)
        SUM=SUM + V
        SUMSQ=SUMSQ + V*V
        TYPE 120,I,V
120     FORMAT("VALUE",I,"IS",E,/)
200     CONTINUE
        SAMP=N
        AVRG=SUM/SAMP
        STD=SQTF(SUMSQ/SAMP - AVRG**2)
        TYPE 300,N,AVRG,STD
300     FORMAT("NUMBER OF VALUES",I,"MEAN",E,"STANDARD DEVIATION",E,/)
        END
```

Install
-------

[PDP-8 Disk System Builder](https://svn.so-much-stuff.com/svn/trunk/pdp8/src/dec/dec-d8-sba/dec-d8-sbab-d.pdf)

Download the papertape [dec-d8-sbaf-pd](http://www.bitsavers.org/bits/DEC/pdp8/From_Vince_Slyngstad/dec/dec-d8-sbaf-pb)

```
$ pdp8

PDP-8 simulator V3.8-1
sim> load dec-d8-sbaf-pb
sim> run 200
```

System Formats
--------------

[4k Disk Monitor System](https://svn.so-much-stuff.com/svn/trunk/pdp8/src/dec/dec-08-odsma/dec-08-odsma-a-d.pdf) Appendix B, Pag 97

* Directory Name (DN)
* Storage Allocation Map (SAM)

### Disk

| Block | Name        |
| ----- | ----------- |
| 0o177 | DN1 (USER)  |
| 0o200 | SAM1 (USER) |
| 0o201 | DN2 (USER)  |
| 0o202 | DN3 (USER)  |
| ...   | Data        |
| 0o373 | Scratch     |
| 0o374 | Scratch     |
| 0o375 | Scratch     |


### DECtape

| Block | Name        |
| ----- | ----------- |
| 0o005 | Scratch     |
| 0o006 | Scratch     |
| 0o007 | Scratch     |
| 0o177 | DN1 (USER)  |
| 0o200 | SAM1 (USER) |
| 0o201 | DN2 (USER)  |
| 0o202 | SAM2 (USER) |
| 0o203 | SAM3 (USER) |
| 0o204 | SAM4 (USER) |
| 0o205 | SAM5 (USER) |
| 0o206 | SAM6 (USER) |
| 0o207 | DN3 (USER)  |

References
----------

* [PDP-8 4K Disk Monitor System](https://svn.so-much-stuff.com/svn/trunk/pdp8/src/dec/dec-08-odsma/dec-08-odsma-a-d.pdf)
* [PDP-8 Disc System Builder](https://svn.so-much-stuff.com/svn/trunk/pdp8/src/dec/dec-d8-sba/dec-d8-sbab-d.pdf)

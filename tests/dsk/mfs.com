CREATE/ALLOCATE:280 mfs.dsk
INITIALIZE/MFS /NAME:"XFERX Test" mfs.dsk
MOUNT/MFS pr: mfs.dsk
COPY/ASCII data/1.txt pr:
COPY/ASCII data/2.txt pr:
COPY/ASCII data/5.txt pr:
COPY/ASCII data/10.txt pr:
COPY/ASCII data/20.txt pr:
COPY/ASCII data/50.txt pr:
COPY/ASCII data/100.txt pr:
COPY/ASCII data/200.txt pr:
COPY/ASCII data/500.txt pr:
COPY/ASCII data/1000.txt pr:
COPY /TO-FORK:RESOURCE data/1.txt pr:100.txt
COPY /TO-FORK:RESOURCE data/1.txt pr:200.txt
COPY /TO-FORK:RESOURCE data/1.txt pr:500.txt
COPY /TO-FORK:RESOURCE data/1.txt pr:1000.txt
COPY data/fish.pntg pr:
DIR pr:
EX pr:
